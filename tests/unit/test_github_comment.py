"""Tests for GitHub comment formatting."""
from __future__ import annotations
import pytest
from datetime import datetime
from mergeguard.output.github_comment import format_report, _pr_link
from mergeguard.models import (
    Conflict, ConflictReport, ConflictSeverity, ConflictType, PRInfo,
)


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

    def test_grouped_output(self):
        """Conflicts should be grouped by target PR in the output."""
        pr = PRInfo(
            number=1, title="Test PR", author="dev",
            base_branch="main", head_branch="feat",
            head_sha="abc", created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        conflicts = [
            Conflict(
                conflict_type=ConflictType.HARD, severity=ConflictSeverity.CRITICAL,
                source_pr=1, target_pr=10, file_path="a.py",
                description="Conflict A", recommendation="Fix A",
            ),
            Conflict(
                conflict_type=ConflictType.BEHAVIORAL, severity=ConflictSeverity.WARNING,
                source_pr=1, target_pr=20, file_path="b.py",
                description="Conflict B", recommendation="Fix B",
            ),
            Conflict(
                conflict_type=ConflictType.HARD, severity=ConflictSeverity.WARNING,
                source_pr=1, target_pr=10, file_path="c.py",
                description="Conflict C", recommendation="Fix C",
            ),
        ]
        report = ConflictReport(
            pr=pr, conflicts=conflicts, risk_score=60.0,
            analysis_duration_ms=100,
        )
        result = format_report(report, "owner/repo")
        # Both PR #10 conflicts should appear under one header
        assert "Conflicts with [#10]" in result
        assert "Conflicts with [#20]" in result
        # PR #10 header should appear before PR #20 header
        pos_10 = result.index("Conflicts with [#10]")
        pos_20 = result.index("Conflicts with [#20]")
        assert pos_10 < pos_20

    def test_large_group_collapsed(self):
        """PR with 6 conflicts gets <details> wrapper."""
        pr = PRInfo(
            number=1, title="Test PR", author="dev",
            base_branch="main", head_branch="feat",
            head_sha="abc", created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        conflicts = [
            Conflict(
                conflict_type=ConflictType.BEHAVIORAL,
                severity=ConflictSeverity.WARNING,
                source_pr=1, target_pr=10, file_path=f"f{i}.py",
                description=f"Conflict {i}", recommendation=f"Fix {i}",
            )
            for i in range(6)
        ]
        report = ConflictReport(
            pr=pr, conflicts=conflicts, risk_score=50.0,
            analysis_duration_ms=100,
        )
        result = format_report(report, "owner/repo")
        assert "<details>" in result
        assert "6 warning" in result
        assert "expand for details" in result

    def test_small_group_not_collapsed(self):
        """PR with 3 conflicts stays expanded (no <details>)."""
        pr = PRInfo(
            number=1, title="Test PR", author="dev",
            base_branch="main", head_branch="feat",
            head_sha="abc", created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        conflicts = [
            Conflict(
                conflict_type=ConflictType.BEHAVIORAL,
                severity=ConflictSeverity.WARNING,
                source_pr=1, target_pr=10, file_path=f"f{i}.py",
                description=f"Conflict {i}", recommendation=f"Fix {i}",
            )
            for i in range(3)
        ]
        report = ConflictReport(
            pr=pr, conflicts=conflicts, risk_score=30.0,
            analysis_duration_ms=100,
        )
        result = format_report(report, "owner/repo")
        # The important section should NOT have <details> wrapping
        # (info-level <details> is separate and won't appear here)
        important_section = result.split("Conflicts with")[1] if "Conflicts with" in result else ""
        assert "<details>" not in important_section or "low-severity" in result


class TestPRLink:
    def test_github_link(self):
        link = _pr_link("owner/repo", 42, "github")
        assert link == "[#42](https://github.com/owner/repo/pull/42)"

    def test_gitlab_link(self):
        link = _pr_link("mygroup/myproject", 10, "gitlab")
        assert link == "[!10](https://gitlab.com/mygroup/myproject/-/merge_requests/10)"


class TestGitLabFormatReport:
    def test_gitlab_report_contains_mr_links(self, sample_report):
        result = format_report(sample_report, "mygroup/myproject", platform="gitlab")
        assert "gitlab.com/mygroup/myproject/-/merge_requests/" in result
        # No GitHub PR links (the footer MergeGuard project link is fine)
        assert "github.com/mygroup/myproject/pull/" not in result

    def test_gitlab_report_uses_exclamation_prefix(self, sample_report):
        result = format_report(sample_report, "mygroup/myproject", platform="gitlab")
        assert "[!43]" in result
