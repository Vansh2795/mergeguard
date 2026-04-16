"""Tests for FileBasedSCMClient — verify it serves fixture data correctly."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# benchmarks/ is at repo root, not a package in src/
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from benchmarks.file_client import FileBasedSCMClient  # noqa: E402
from mergeguard.models import ConflictType, FileChangeStatus, MergeGuardConfig  # noqa: E402


def _make_fixture(
    prs=None,
    file_contents=None,
) -> dict:
    """Build a minimal fixture dict."""
    return {
        "repo": "owner/repo",
        "prs": prs or [],
        "file_contents": file_contents or {},
    }


def _make_pr_data(
    number: int,
    files: list[dict] | None = None,
    base_branch: str = "main",
    head_sha: str = "abc123",
) -> dict:
    return {
        "number": number,
        "title": f"PR {number}",
        "author": "dev",
        "base_branch": base_branch,
        "head_branch": f"feature-{number}",
        "head_sha": head_sha,
        "created_at": "2026-01-15T10:00:00",
        "updated_at": "2026-01-16T14:00:00",
        "changed_files": files or [],
    }


def _make_file_data(
    path: str,
    status: str = "modified",
    patch: str = "@@ -1,3 +1,3 @@\n-old\n+new\n context\n",
) -> dict:
    return {
        "path": path,
        "status": status,
        "additions": 1,
        "deletions": 1,
        "patch": patch,
    }


class TestGetFileContent:
    def test_returns_stored_content(self):
        fixture = _make_fixture(file_contents={"main:src/app.py": "def hello(): pass"})
        client = FileBasedSCMClient(fixture)
        assert client.get_file_content("src/app.py", "main") == "def hello(): pass"

    def test_returns_none_for_missing(self):
        fixture = _make_fixture()
        client = FileBasedSCMClient(fixture)
        assert client.get_file_content("nonexistent.py", "main") is None

    def test_distinguishes_refs(self):
        fixture = _make_fixture(
            file_contents={
                "main:file.py": "version_1",
                "abc123:file.py": "version_2",
            }
        )
        client = FileBasedSCMClient(fixture)
        assert client.get_file_content("file.py", "main") == "version_1"
        assert client.get_file_content("file.py", "abc123") == "version_2"


class TestGetOpenPrs:
    def test_returns_all_captured(self):
        prs = [_make_pr_data(i) for i in range(1, 6)]
        fixture = _make_fixture(prs=prs)
        client = FileBasedSCMClient(fixture)
        result = client.get_open_prs()
        assert len(result) == 5
        assert result[0].number == 1
        assert result[4].number == 5

    def test_respects_max_count(self):
        prs = [_make_pr_data(i) for i in range(1, 11)]
        fixture = _make_fixture(prs=prs)
        client = FileBasedSCMClient(fixture)
        result = client.get_open_prs(max_count=3)
        assert len(result) == 3


class TestGetPrFiles:
    def test_returns_changed_files(self):
        files = [
            _make_file_data("src/a.py"),
            _make_file_data("src/b.py"),
            _make_file_data("src/c.py"),
        ]
        fixture = _make_fixture(prs=[_make_pr_data(42, files=files)])
        client = FileBasedSCMClient(fixture)
        result = client.get_pr_files(42)
        assert len(result) == 3
        assert result[0].path == "src/a.py"
        assert result[0].status == FileChangeStatus.MODIFIED

    def test_returns_empty_for_unknown_pr(self):
        fixture = _make_fixture(prs=[_make_pr_data(42)])
        client = FileBasedSCMClient(fixture)
        assert client.get_pr_files(999) == []


class TestGetPrDiff:
    def test_reconstructs_from_patches(self):
        files = [_make_file_data("src/app.py", patch="@@ -1,3 +1,3 @@\n-old\n+new\n")]
        fixture = _make_fixture(prs=[_make_pr_data(42, files=files)])
        client = FileBasedSCMClient(fixture)
        diff = client.get_pr_diff(42)
        assert "diff --git" in diff
        assert "src/app.py" in diff
        assert "+new" in diff


class TestGetPr:
    def test_returns_matching_pr(self):
        fixture = _make_fixture(prs=[_make_pr_data(42), _make_pr_data(43)])
        client = FileBasedSCMClient(fixture)
        pr = client.get_pr(43)
        assert pr.number == 43
        assert pr.title == "PR 43"

    def test_raises_for_missing(self):
        fixture = _make_fixture(prs=[_make_pr_data(42)])
        client = FileBasedSCMClient(fixture)
        with pytest.raises(ValueError, match="not found"):
            client.get_pr(999)


class TestEngineIntegration:
    @patch("mergeguard.core.engine.GitHubClient")
    def test_full_analysis_with_file_client(self, mock_gh_class):
        """End-to-end: FileBasedSCMClient drives real engine to detect a HARD conflict."""
        patch_a = "@@ -10,5 +10,5 @@\n-    old_line\n+    new_line_a\n context\n"
        patch_b = "@@ -10,5 +10,5 @@\n-    old_line\n+    new_line_b\n context\n"

        fixture = _make_fixture(
            prs=[
                _make_pr_data(
                    100, files=[_make_file_data("src/shared.py", patch=patch_a)], head_sha="sha100"
                ),
                _make_pr_data(
                    101, files=[_make_file_data("src/shared.py", patch=patch_b)], head_sha="sha101"
                ),
            ],
            file_contents={
                "main:src/shared.py": "def hello():\n    old_line\n    return True\n",
                "sha100:src/shared.py": "def hello():\n    new_line_a\n    return True\n",
                "sha101:src/shared.py": "def hello():\n    new_line_b\n    return True\n",
            },
        )

        client = FileBasedSCMClient(fixture)

        from mergeguard.core.engine import MergeGuardEngine

        cfg = MergeGuardConfig(check_regressions=False)
        engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=cfg)
        # Replace the real client with our file-based one
        engine._client = client

        report = engine.analyze_pr(100)

        hard = [c for c in report.conflicts if c.conflict_type == ConflictType.HARD]
        assert len(hard) >= 1, (
            f"Expected at least 1 HARD conflict, got {len(hard)}. "
            f"All conflicts: {[(c.conflict_type.value, c.file_path) for c in report.conflicts]}"
        )
        assert hard[0].file_path == "src/shared.py"
