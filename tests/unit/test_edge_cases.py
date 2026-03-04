"""Edge case tests for PRs with unusual inputs (T-1)."""

from __future__ import annotations

import threading
from datetime import datetime
from unittest.mock import MagicMock

from mergeguard.models import (
    ChangedFile,
    FileChangeStatus,
    MergeGuardConfig,
    PRInfo,
)


def _make_engine():
    """Create a minimal MergeGuardEngine with mocked dependencies."""
    from mergeguard.core.engine import MergeGuardEngine

    engine = MergeGuardEngine.__new__(MergeGuardEngine)
    engine._content_cache = {}
    engine._cache_lock = threading.Lock()
    engine._symbol_index = MagicMock()
    engine._symbol_index.get_symbols.return_value = []
    engine._symbol_index.get_symbols_and_call_graph.return_value = ([], {})
    engine._config = MergeGuardConfig()
    engine._ignore_res = []
    engine._client = MagicMock()
    return engine


def _make_pr(number: int, files: list[ChangedFile] | None = None) -> PRInfo:
    return PRInfo(
        number=number,
        title=f"PR {number}",
        author="dev",
        base_branch="main",
        head_branch=f"branch-{number}",
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
        changed_files=files or [],
    )


class TestPRWithZeroChangedFiles:
    """PR with 0 changed files should not crash."""

    def test_enrich_pr_no_files(self):
        engine = _make_engine()
        pr = _make_pr(1)
        engine._enrich_pr(pr)
        assert len(pr.changed_symbols) == 0
        assert len(pr.skipped_files) == 0


class TestPRWithOnlyDeletedFiles:
    """PR with only deleted files should produce 0 changed symbols."""

    def test_only_deleted_files(self):
        engine = _make_engine()
        pr = _make_pr(1, [
            ChangedFile(
                path="src/old.py", status=FileChangeStatus.REMOVED,
                additions=0, deletions=10,
                patch="@@ -1,10 +0,0 @@\n-old code",
            ),
            ChangedFile(
                path="src/legacy.py", status=FileChangeStatus.REMOVED,
                additions=0, deletions=25,
                patch="@@ -1,25 +0,0 @@\n-more old code",
            ),
        ])
        engine._enrich_pr(pr)
        assert len(pr.changed_symbols) == 0


class TestPRWithOnlyBinaryFiles:
    """PR with only binary files should skip all and add to skipped_files."""

    def test_only_binary_files(self):
        engine = _make_engine()
        engine._get_file_content_cached = MagicMock(
            return_value="header\x00binary_data_here"
        )
        pr = _make_pr(1, [
            ChangedFile(
                path="assets/image.png", status=FileChangeStatus.MODIFIED,
                additions=1, deletions=1,
                patch="@@ -1,3 +1,3 @@\n-old\n+new",
            ),
        ])
        engine._enrich_pr(pr)
        assert len(pr.changed_symbols) == 0
        assert "assets/image.png" in pr.skipped_files


class TestPRWithAllFilesFilteredByIgnoredPaths:
    """PR where all files are filtered by ignored_paths should produce 0 symbols."""

    def test_all_files_ignored(self):
        import fnmatch
        import re

        engine = _make_engine()
        engine._ignore_res = [
            re.compile(fnmatch.translate("package-lock.json")),
            re.compile(fnmatch.translate("*.min.js")),
        ]
        pr = _make_pr(1, [
            ChangedFile(
                path="package-lock.json", status=FileChangeStatus.MODIFIED,
                additions=100, deletions=50,
                patch="@@ -1,3 +1,3 @@\n-old\n+new",
            ),
            ChangedFile(
                path="dist/bundle.min.js", status=FileChangeStatus.MODIFIED,
                additions=500, deletions=200,
                patch="@@ -1,3 +1,3 @@\n-old\n+new",
            ),
        ])
        engine._enrich_pr(pr)
        assert len(pr.changed_symbols) == 0
        assert len(pr.changed_files) == 0


class TestEmptyFileContentFromAPI:
    """Empty file content from API should be handled gracefully."""

    def test_empty_content_skipped(self):
        engine = _make_engine()
        engine._get_file_content_cached = MagicMock(return_value="")
        pr = _make_pr(1, [
            ChangedFile(
                path="src/empty.py", status=FileChangeStatus.MODIFIED,
                additions=1, deletions=0,
                patch="@@ -1,3 +1,3 @@\n-old\n+new",
            ),
        ])
        engine._enrich_pr(pr)
        assert len(pr.changed_symbols) == 0
