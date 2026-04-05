"""Smoke tests for output formatters — verify they produce output without crashing."""

from __future__ import annotations

import json
from datetime import datetime

from mergeguard.models import (
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    PRInfo,
)


def _make_report() -> ConflictReport:
    pr = PRInfo(
        number=42,
        title="Test PR",
        author="alice",
        base_branch="main",
        head_branch="feature",
        head_sha="abc123",
        created_at=datetime(2026, 1, 15),
        updated_at=datetime(2026, 1, 16),
    )
    conflict = Conflict(
        conflict_type=ConflictType.HARD,
        severity=ConflictSeverity.WARNING,
        source_pr=42,
        target_pr=43,
        file_path="src/main.py",
        description="Overlapping changes.",
        recommendation="Coordinate.",
    )
    return ConflictReport(
        pr=pr,
        conflicts=[conflict],
        risk_score=55.0,
        risk_factors={"conflict_severity": 80.0},
        analysis_duration_ms=500,
    )


class TestJsonReport:
    def test_produces_valid_json(self):
        from mergeguard.output.json_report import format_json_report

        report = _make_report()
        result = format_json_report(report)
        parsed = json.loads(result)
        assert "pr" in parsed
        assert "conflicts" in parsed


class TestHtmlReport:
    def test_produces_html_string(self):
        from mergeguard.output.html_report import format_html_report

        report = _make_report()
        html = format_html_report(report, "owner/repo")
        assert "<html" in html.lower()
        assert "42" in html


class TestDashboardHtml:
    def test_produces_html_string(self):
        from mergeguard.output.dashboard_html import format_dashboard_html

        report = _make_report()
        html = format_dashboard_html([report], "owner/repo")
        assert "<html" in html.lower()


class TestBadgeOutput:
    def test_generates_svg(self):
        from mergeguard.output.badge import generate_risk_badge

        svg = generate_risk_badge(55.0)
        assert "<svg" in svg


class TestSarifOutput:
    def test_produces_valid_sarif(self):
        from mergeguard.output.sarif import format_sarif

        report = _make_report()
        result = format_sarif(report)
        parsed = json.loads(result)
        assert "runs" in parsed


class TestTerminalOutput:
    def test_does_not_crash(self):
        from mergeguard.output.terminal import display_report

        report = _make_report()
        display_report(report)
