"""Integration tests for the full analyze_pr pipeline."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from mergeguard.core.engine import MergeGuardEngine
from mergeguard.models import (
    ChangedFile,
    ConflictType,
    FileChangeStatus,
    MergeGuardConfig,
    PRInfo,
)

# Patches for same-file same-line conflict scenario
PATCH_A = "@@ -10,5 +10,5 @@\n-    old_line\n+    new_line_a\n context\n"
PATCH_B = "@@ -10,5 +10,5 @@\n-    old_line\n+    new_line_b\n context\n"


def _make_pr(number: int, title: str = "PR", author: str = "dev") -> PRInfo:
    return PRInfo(
        number=number,
        title=title,
        author=author,
        base_branch="main",
        head_branch=f"feature/{number}",
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 15),
        updated_at=datetime(2026, 1, 15),
    )


class TestEngineSameFileConflict:
    """Two PRs modifying the same lines → at least 1 HARD conflict."""

    @patch("mergeguard.core.engine.GitHubClient")
    def test_same_file_same_lines_produces_conflict(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        target_pr = _make_pr(1, "Change line 10", "alice")
        other_pr = _make_pr(2, "Also change line 10", "bob")

        target_files = [
            ChangedFile(
                path="src/shared.py",
                status=FileChangeStatus.MODIFIED,
                additions=1,
                deletions=1,
                patch=PATCH_A,
            )
        ]
        other_files = [
            ChangedFile(
                path="src/shared.py",
                status=FileChangeStatus.MODIFIED,
                additions=1,
                deletions=1,
                patch=PATCH_B,
            )
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 1 else other_files
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = "def hello():\n    old_line\n    return True\n"
        mock_client.get_pr_diff.return_value = ""
        mock_client.rate_limit_remaining = 5000

        cfg = MergeGuardConfig(check_regressions=False)
        engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=cfg)
        report = engine.analyze_pr(1)

        assert report.pr.number == 1
        hard_conflicts = [
            c for c in report.conflicts if c.conflict_type == ConflictType.HARD
        ]
        assert len(hard_conflicts) >= 1, (
            f"Expected at least 1 HARD conflict, got {report.conflicts}"
        )


class TestEngineDifferentFiles:
    """Two PRs modifying different files → 0 conflicts."""

    @patch("mergeguard.core.engine.GitHubClient")
    def test_different_files_no_conflicts(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        target_pr = _make_pr(10, "Add auth module", "alice")
        other_pr = _make_pr(11, "Add logging module", "bob")

        target_files = [
            ChangedFile(
                path="src/auth.py",
                status=FileChangeStatus.MODIFIED,
                additions=5,
                deletions=0,
                patch=PATCH_A,
            )
        ]
        other_files = [
            ChangedFile(
                path="src/logging.py",
                status=FileChangeStatus.MODIFIED,
                additions=5,
                deletions=0,
                patch=PATCH_B,
            )
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 10 else other_files
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = "def hello():\n    old_line\n    return True\n"
        mock_client.get_pr_diff.return_value = ""
        mock_client.rate_limit_remaining = 5000

        cfg = MergeGuardConfig(check_regressions=False)
        engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=cfg)
        report = engine.analyze_pr(10)

        assert report.pr.number == 10
        assert len(report.conflicts) == 0, (
            f"Expected 0 conflicts for different files, got {report.conflicts}"
        )
