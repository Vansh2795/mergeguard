"""Tests for patch backfill logic."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mergeguard.core.engine import MergeGuardEngine, _extract_file_patches
from mergeguard.models import (
    ChangedFile,
    FileChangeStatus,
    MergeGuardConfig,
    PRInfo,
)


def _make_pr(number=1, files=None):
    pr = PRInfo(
        number=number,
        title=f"PR {number}",
        author="dev",
        base_branch="main",
        head_branch=f"branch-{number}",
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    pr.changed_files = files or []
    return pr


SINGLE_FILE_DIFF = """\
diff --git a/src/utils.py b/src/utils.py
index abc123..def456 100644
--- a/src/utils.py
+++ b/src/utils.py
@@ -10,3 +10,5 @@
 context line
-old line
+new line
+added line
"""

MULTI_FILE_DIFF = """\
diff --git a/src/a.py b/src/a.py
index 111..222 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,3 +1,4 @@
 context
+new in a
diff --git a/src/b.py b/src/b.py
index 333..444 100644
--- a/src/b.py
+++ b/src/b.py
@@ -5,2 +5,3 @@
 context
-removed in b
+replaced in b
"""

RENAME_DIFF = """\
diff --git a/old_name.py b/new_name.py
similarity index 90%
rename from old_name.py
rename to new_name.py
--- a/old_name.py
+++ b/new_name.py
@@ -1,3 +1,3 @@
-old content
+new content
"""

BINARY_DIFF = """\
diff --git a/image.png b/image.png
Binary files /dev/null and b/image.png differ
"""


class TestExtractFilePatches:
    def test_single_file(self):
        patches = _extract_file_patches(SINGLE_FILE_DIFF)
        assert "src/utils.py" in patches
        assert patches["src/utils.py"].startswith("@@ -10,3 +10,5 @@")

    def test_multi_file(self):
        patches = _extract_file_patches(MULTI_FILE_DIFF)
        assert "src/a.py" in patches
        assert "src/b.py" in patches
        assert "+new in a" in patches["src/a.py"]
        assert "+replaced in b" in patches["src/b.py"]

    def test_rename(self):
        patches = _extract_file_patches(RENAME_DIFF)
        assert "new_name.py" in patches
        assert "+new content" in patches["new_name.py"]

    def test_empty_diff(self):
        patches = _extract_file_patches("")
        assert patches == {}

    def test_binary_file_no_hunk(self):
        patches = _extract_file_patches(BINARY_DIFF)
        # Binary diffs have no @@ hunk headers
        assert "image.png" not in patches


class TestBackfillTruncatedPatches:
    def _make_engine(self):
        with patch.object(MergeGuardEngine, "__init__", lambda self, *a, **kw: None):
            engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._client = MagicMock()
        engine._config = MergeGuardConfig()
        return engine

    def test_all_patches_present_no_fetch(self):
        """When all files have patches, no API call should be made."""
        engine = self._make_engine()
        pr = _make_pr(files=[
            ChangedFile(path="a.py", status=FileChangeStatus.MODIFIED, patch="@@ ...\n+ok"),
            ChangedFile(path="b.py", status=FileChangeStatus.MODIFIED, patch="@@ ...\n+ok"),
        ])
        engine._backfill_truncated_patches(pr)
        engine._client.get_pr_diff.assert_not_called()

    def test_missing_patch_triggers_backfill(self):
        """Files with patch=None should be backfilled from full diff."""
        engine = self._make_engine()
        engine._client.get_pr_diff.return_value = SINGLE_FILE_DIFF

        cf = ChangedFile(path="src/utils.py", status=FileChangeStatus.MODIFIED, patch=None)
        pr = _make_pr(files=[cf])

        engine._backfill_truncated_patches(pr)
        engine._client.get_pr_diff.assert_called_once_with(1)
        assert cf.patch is not None
        assert cf.patch.startswith("@@ -10,3 +10,5 @@")

    def test_deleted_file_skipped(self):
        """REMOVED files should not trigger backfill."""
        engine = self._make_engine()
        pr = _make_pr(files=[
            ChangedFile(path="gone.py", status=FileChangeStatus.REMOVED, patch=None),
        ])
        engine._backfill_truncated_patches(pr)
        engine._client.get_pr_diff.assert_not_called()

    def test_api_failure_graceful(self):
        """API failure should log warning but not raise."""
        engine = self._make_engine()
        engine._client.get_pr_diff.side_effect = httpx.HTTPError("rate limited")

        cf = ChangedFile(path="src/utils.py", status=FileChangeStatus.MODIFIED, patch=None)
        pr = _make_pr(files=[cf])

        # Should not raise
        engine._backfill_truncated_patches(pr)
        assert cf.patch is None  # Still None after failure

    def test_rename_backfill_via_previous_path(self):
        """Renamed files should try previous_path as fallback."""
        engine = self._make_engine()
        engine._client.get_pr_diff.return_value = RENAME_DIFF

        cf = ChangedFile(
            path="new_name.py",
            status=FileChangeStatus.RENAMED,
            patch=None,
            previous_path="old_name.py",
        )
        pr = _make_pr(files=[cf])

        engine._backfill_truncated_patches(pr)
        assert cf.patch is not None
