"""Tests for GitHub comment formatting."""
from __future__ import annotations
import pytest
from mergeguard.output.github_comment import format_report


class TestFormatReport:
    def test_empty_report(self, empty_report):
        result = format_report(empty_report, "owner/repo")
        assert "No cross-PR conflicts detected" in result

    def test_report_with_conflicts(self, sample_report):
        result = format_report(sample_report, "owner/repo")
        assert "Risk Score" in result
        assert "75/100" in result

    def test_report_contains_pr_links(self, sample_report):
        result = format_report(sample_report, "owner/repo")
        assert "owner/repo/pull/" in result

    def test_report_footer(self, sample_report):
        result = format_report(sample_report, "owner/repo")
        assert "MergeGuard" in result
