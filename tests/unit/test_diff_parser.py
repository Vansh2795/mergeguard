"""Tests for diff_parser module."""
from __future__ import annotations
import pytest
from mergeguard.analysis.diff_parser import parse_unified_diff, FileDiff, DiffHunk


class TestParseUnifiedDiff:
    def test_parse_simple_modification(self):
        diff = (
            "diff --git a/file.py b/file.py\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -10,3 +10,4 @@\n"
            " context\n"
            "-old line\n"
            "+new line\n"
            "+added line\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        assert result[0].path == "file.py"
        assert len(result[0].hunks) == 1

    def test_parse_new_file(self):
        diff = (
            "diff --git a/new.py b/new.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+line 1\n"
            "+line 2\n"
            "+line 3\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        assert result[0].is_new is True

    def test_parse_deleted_file(self):
        diff = (
            "diff --git a/old.py b/old.py\n"
            "deleted file mode 100644\n"
            "--- a/old.py\n"
            "+++ /dev/null\n"
            "@@ -1,3 +0,0 @@\n"
            "-line 1\n"
            "-line 2\n"
            "-line 3\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        assert result[0].is_deleted is True

    def test_parse_multi_file_diff(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/b.py b/b.py\n"
            "--- a/b.py\n"
            "+++ b/b.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 2

    def test_parse_rename(self):
        diff = (
            "diff --git a/old_name.py b/new_name.py\n"
            "--- a/old_name.py\n"
            "+++ b/new_name.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
        )
        result = parse_unified_diff(diff)
        assert result[0].old_path == "old_name.py"
        assert result[0].path == "new_name.py"

    def test_modified_line_ranges(self):
        diff = (
            "diff --git a/file.py b/file.py\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -10,3 +10,5 @@\n"
            " context\n"
            "+added 1\n"
            "+added 2\n"
            "+added 3\n"
            " context\n"
        )
        result = parse_unified_diff(diff)
        ranges = result[0].all_modified_line_ranges
        assert len(ranges) == 1
        assert ranges[0][0] <= ranges[0][1]

    def test_empty_diff(self):
        result = parse_unified_diff("")
        assert result == []
