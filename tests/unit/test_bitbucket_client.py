"""Tests for Bitbucket Cloud client — diffstat parsing, patch attachment, datetime parsing."""

from __future__ import annotations

import pytest

from mergeguard.integrations.bitbucket_client import (
    BitbucketClient,
    _parse_bitbucket_datetime,
    _split_diff_by_file,
)
from mergeguard.models import FileChangeStatus


class TestDiffstatToChangedFile:
    """Tests for BitbucketClient._diffstat_to_changed_file static method."""

    def test_modified_file(self):
        entry = {
            "status": "modified",
            "lines_added": 10,
            "lines_removed": 3,
            "new": {"path": "src/app.py"},
            "old": {"path": "src/app.py"},
        }
        result = BitbucketClient._diffstat_to_changed_file(entry)
        assert result.path == "src/app.py"
        assert result.status == FileChangeStatus.MODIFIED
        assert result.additions == 10
        assert result.deletions == 3
        assert result.patch is None
        assert result.previous_path is None

    def test_added_file(self):
        entry = {
            "status": "added",
            "lines_added": 50,
            "lines_removed": 0,
            "new": {"path": "src/new_module.py"},
            "old": None,
        }
        result = BitbucketClient._diffstat_to_changed_file(entry)
        assert result.path == "src/new_module.py"
        assert result.status == FileChangeStatus.ADDED
        assert result.additions == 50
        assert result.deletions == 0

    def test_removed_file(self):
        entry = {
            "status": "removed",
            "lines_added": 0,
            "lines_removed": 30,
            "new": None,
            "old": {"path": "src/legacy.py"},
        }
        result = BitbucketClient._diffstat_to_changed_file(entry)
        assert result.path == "src/legacy.py"
        assert result.status == FileChangeStatus.REMOVED

    def test_renamed_file(self):
        entry = {
            "status": "renamed",
            "lines_added": 5,
            "lines_removed": 2,
            "new": {"path": "src/auth/handler.py"},
            "old": {"path": "src/auth_handler.py"},
        }
        result = BitbucketClient._diffstat_to_changed_file(entry)
        assert result.path == "src/auth/handler.py"
        assert result.status == FileChangeStatus.RENAMED
        assert result.previous_path == "src/auth_handler.py"

    def test_unknown_status_defaults_to_modified(self):
        entry = {
            "status": "conflict",
            "lines_added": 1,
            "lines_removed": 1,
            "new": {"path": "src/app.py"},
            "old": {"path": "src/app.py"},
        }
        result = BitbucketClient._diffstat_to_changed_file(entry)
        assert result.status == FileChangeStatus.MODIFIED

    def test_missing_line_counts_default_to_zero(self):
        entry = {
            "status": "modified",
            "new": {"path": "src/app.py"},
            "old": {"path": "src/app.py"},
        }
        result = BitbucketClient._diffstat_to_changed_file(entry)
        assert result.additions == 0
        assert result.deletions == 0

    def test_null_line_counts_default_to_zero(self):
        entry = {
            "status": "modified",
            "lines_added": None,
            "lines_removed": None,
            "new": {"path": "src/app.py"},
            "old": {"path": "src/app.py"},
        }
        result = BitbucketClient._diffstat_to_changed_file(entry)
        assert result.additions == 0
        assert result.deletions == 0


class TestSplitDiffByFile:
    """Tests for the _split_diff_by_file helper."""

    def test_single_file_diff(self):
        raw_diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            "+new_line\n"
            " line2\n"
        )
        patches = _split_diff_by_file(raw_diff)
        assert "src/app.py" in patches
        assert "@@ -1,3 +1,4 @@" in patches["src/app.py"]

    def test_multiple_file_diff(self):
        raw_diff = (
            "diff --git a/src/a.py b/src/a.py\n"
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+added_a\n"
            "diff --git a/src/b.py b/src/b.py\n"
            "--- a/src/b.py\n"
            "+++ b/src/b.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+added_b\n"
        )
        patches = _split_diff_by_file(raw_diff)
        assert len(patches) == 2
        assert "src/a.py" in patches
        assert "src/b.py" in patches
        assert "+added_a" in patches["src/a.py"]
        assert "+added_b" in patches["src/b.py"]

    def test_empty_diff(self):
        assert _split_diff_by_file("") == {}

    def test_renamed_file_diff(self):
        raw_diff = (
            "diff --git a/old_name.py b/new_name.py\n"
            "similarity index 90%\n"
            "rename from old_name.py\n"
            "rename to new_name.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+changed\n"
        )
        patches = _split_diff_by_file(raw_diff)
        assert "new_name.py" in patches


class TestParseBitbucketDatetime:
    """Tests for _parse_bitbucket_datetime."""

    def test_standard_format(self):
        dt = _parse_bitbucket_datetime("2024-01-15T10:30:00.123456+00:00")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30

    def test_z_suffix(self):
        dt = _parse_bitbucket_datetime("2024-06-01T12:00:00Z")
        assert dt.year == 2024
        assert dt.month == 6

    def test_timezone_aware(self):
        dt = _parse_bitbucket_datetime("2024-01-15T10:30:00+00:00")
        assert dt.tzinfo is not None


class TestBitbucketClientInit:
    """Tests for BitbucketClient constructor validation."""

    def test_requires_colon_in_token(self):
        with pytest.raises(ValueError, match="username:app_password"):
            BitbucketClient(token="just-a-token", repo_full_name="workspace/repo")

    def test_requires_slash_in_repo(self):
        with pytest.raises(ValueError, match="workspace/repo"):
            BitbucketClient(token="user:pass", repo_full_name="noslash")

    def test_valid_init(self):
        client = BitbucketClient(token="user:pass", repo_full_name="workspace/repo")
        assert client._workspace == "workspace"
        assert client._repo_slug == "repo"
        client.close()

    def test_context_manager(self):
        with BitbucketClient(token="user:pass", repo_full_name="ws/repo") as client:
            assert client._workspace == "ws"
