"""Tests for inline annotation formatting."""

from __future__ import annotations

from datetime import datetime

from mergeguard.integrations.protocol import ReviewComment
from mergeguard.models import (
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    PRInfo,
)
from mergeguard.output.inline_annotations import (
    format_review_comments,
    format_review_summary,
)


def _make_pr() -> PRInfo:
    return PRInfo(
        number=1,
        title="Test PR",
        author="dev",
        base_branch="main",
        head_branch="feat",
        head_sha="abc",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _make_conflict(
    *,
    conflict_type: ConflictType = ConflictType.HARD,
    severity: ConflictSeverity = ConflictSeverity.CRITICAL,
    source_lines: tuple[int, int] | None = (10, 20),
    target_lines: tuple[int, int] | None = (15, 25),
    file_path: str = "src/app.py",
    symbol_name: str | None = "process_data",
    fix_suggestion: str | None = None,
) -> Conflict:
    return Conflict(
        conflict_type=conflict_type,
        severity=severity,
        source_pr=1,
        target_pr=2,
        file_path=file_path,
        symbol_name=symbol_name,
        description="Test conflict description.",
        recommendation="Test recommendation.",
        source_lines=source_lines,
        target_lines=target_lines,
        fix_suggestion=fix_suggestion,
    )


class TestFormatReviewComments:
    def test_produces_review_comments(self):
        """Conflicts with source_lines produce ReviewComment objects."""
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[_make_conflict()],
            risk_score=80.0,
        )
        comments = format_review_comments(report, "owner/repo")
        assert len(comments) == 1
        assert isinstance(comments[0], ReviewComment)
        assert comments[0].path == "src/app.py"
        assert comments[0].line == 10

    def test_skips_conflicts_without_source_lines(self):
        """Conflicts without source_lines are skipped."""
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[
                _make_conflict(source_lines=(10, 20)),
                _make_conflict(source_lines=None, file_path="other.py"),
            ],
            risk_score=60.0,
        )
        comments = format_review_comments(report, "owner/repo")
        assert len(comments) == 1
        assert comments[0].path == "src/app.py"

    def test_max_comments_cap(self):
        """Output is capped at max_comments."""
        conflicts = [_make_conflict(file_path=f"f{i}.py") for i in range(10)]
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=conflicts,
            risk_score=90.0,
        )
        comments = format_review_comments(report, "owner/repo", max_comments=3)
        assert len(comments) == 3

    def test_critical_sorted_first(self):
        """Critical conflicts come before warnings."""
        conflicts = [
            _make_conflict(severity=ConflictSeverity.WARNING, file_path="a.py"),
            _make_conflict(severity=ConflictSeverity.CRITICAL, file_path="b.py"),
        ]
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=conflicts,
            risk_score=70.0,
        )
        comments = format_review_comments(report, "owner/repo")
        assert len(comments) == 2
        # Critical (b.py) should come first
        assert comments[0].path == "b.py"
        assert comments[1].path == "a.py"

    def test_annotation_body_hard_conflict(self):
        """Hard conflict annotation body contains expected elements."""
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[_make_conflict(conflict_type=ConflictType.HARD)],
            risk_score=80.0,
        )
        comments = format_review_comments(report, "owner/repo")
        body = comments[0].body
        assert "Hard Conflict" in body
        assert "PR #2" in body
        assert "`process_data`" in body
        assert "Test conflict description" in body
        assert "Test recommendation" in body

    def test_annotation_body_interface_conflict(self):
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[_make_conflict(conflict_type=ConflictType.INTERFACE)],
            risk_score=80.0,
        )
        comments = format_review_comments(report, "owner/repo")
        assert "Interface Conflict" in comments[0].body

    def test_annotation_body_behavioral_conflict(self):
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[_make_conflict(conflict_type=ConflictType.BEHAVIORAL)],
            risk_score=50.0,
        )
        comments = format_review_comments(report, "owner/repo")
        assert "Behavioral Conflict" in comments[0].body

    def test_annotation_body_duplication_conflict(self):
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[
                _make_conflict(
                    conflict_type=ConflictType.DUPLICATION,
                    severity=ConflictSeverity.INFO,
                )
            ],
            risk_score=20.0,
        )
        comments = format_review_comments(report, "owner/repo")
        assert "Duplication Detected" in comments[0].body

    def test_annotation_body_with_fix_suggestion(self):
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[_make_conflict(fix_suggestion="Rename the function.")],
            risk_score=80.0,
        )
        comments = format_review_comments(report, "owner/repo")
        assert "Suggested fix:" in comments[0].body
        assert "Rename the function." in comments[0].body

    def test_annotation_body_without_symbol(self):
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[_make_conflict(symbol_name=None)],
            risk_score=50.0,
        )
        comments = format_review_comments(report, "owner/repo")
        assert "Symbol:" not in comments[0].body

    def test_empty_report(self):
        report = ConflictReport(pr=_make_pr(), conflicts=[], risk_score=0.0)
        comments = format_review_comments(report, "owner/repo")
        assert comments == []


class TestFormatReviewSummary:
    def test_summary_with_all_inline(self):
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[_make_conflict(), _make_conflict(file_path="b.py")],
            risk_score=70.0,
        )
        result = format_review_summary(report, inline_count=2)
        assert "2" in result
        assert "70/100" in result
        # No skipped message when all are inline
        assert "without line info" not in result

    def test_summary_with_skipped(self):
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[
                _make_conflict(),
                _make_conflict(source_lines=None, file_path="b.py"),
                _make_conflict(source_lines=None, file_path="c.py"),
            ],
            risk_score=60.0,
        )
        result = format_review_summary(report, inline_count=1)
        assert "1 conflict(s) annotated inline" in result
        assert "2 conflict(s) without line info" in result
