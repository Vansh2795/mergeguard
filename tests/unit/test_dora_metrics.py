"""Tests for DORA metrics engine — record and compute functions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mergeguard.core.metrics import (
    _percentile,
    _severity_max,
    compute_dora_metrics,
    record_analysis,
    record_resolution,
)
from mergeguard.models import (
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    PRInfo,
)
from mergeguard.storage.metrics_store import MetricsStore


@pytest.fixture
def store():
    s = MetricsStore(":memory:")
    yield s
    s.close()


def _make_pr(number: int = 42) -> PRInfo:
    return PRInfo(
        number=number,
        title="Test PR",
        author="alice",
        base_branch="main",
        head_branch="feature/test",
        head_sha="abc123",
        created_at=datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC),
    )


def _make_conflict(
    severity: ConflictSeverity = ConflictSeverity.CRITICAL,
    source_pr: int = 42,
    target_pr: int = 43,
) -> Conflict:
    return Conflict(
        conflict_type=ConflictType.HARD,
        severity=severity,
        source_pr=source_pr,
        target_pr=target_pr,
        file_path="src/service.py",
        description="Test conflict",
        recommendation="Fix it",
    )


def _make_report(
    pr_number: int = 42,
    conflicts: list[Conflict] | None = None,
    risk_score: float = 75.0,
) -> ConflictReport:
    return ConflictReport(
        pr=_make_pr(pr_number),
        conflicts=conflicts or [],
        risk_score=risk_score,
        analyzed_at=datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC),
    )


class TestSeverityMax:
    def test_critical(self):
        report = _make_report(conflicts=[_make_conflict(ConflictSeverity.CRITICAL)])
        assert _severity_max(report) == "critical"

    def test_warning(self):
        report = _make_report(conflicts=[_make_conflict(ConflictSeverity.WARNING)])
        assert _severity_max(report) == "warning"

    def test_info(self):
        report = _make_report(conflicts=[_make_conflict(ConflictSeverity.INFO)])
        assert _severity_max(report) == "info"

    def test_mixed_returns_highest(self):
        report = _make_report(
            conflicts=[
                _make_conflict(ConflictSeverity.INFO),
                _make_conflict(ConflictSeverity.CRITICAL),
                _make_conflict(ConflictSeverity.WARNING),
            ]
        )
        assert _severity_max(report) == "critical"

    def test_no_conflicts(self):
        report = _make_report(conflicts=[])
        assert _severity_max(report) == "none"


class TestPercentile:
    def test_empty(self):
        assert _percentile([], 90) == 0.0

    def test_single_value(self):
        assert _percentile([5.0], 90) == 5.0

    def test_p90_of_ten_values(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = _percentile(values, 90)
        assert 9.0 <= result <= 10.0

    def test_p50_is_median(self):
        values = [1, 2, 3, 4, 5]
        assert _percentile(values, 50) == 3.0


class TestRecordAnalysis:
    def test_records_snapshot(self, store: MetricsStore):
        report = _make_report(
            conflicts=[_make_conflict()],
            risk_score=75.0,
        )
        record_analysis(report, "owner/repo", store=store)

        snapshots = store.get_snapshots("owner/repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(snapshots) == 1
        assert snapshots[0].pr_number == 42
        assert snapshots[0].severity_max == "critical"

    def test_skips_empty_conflicts(self, store: MetricsStore):
        report = _make_report(conflicts=[])
        record_analysis(report, "owner/repo", store=store)

        snapshots = store.get_snapshots("owner/repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(snapshots) == 0


class TestRecordResolution:
    def test_marks_resolved(self, store: MetricsStore):
        report = _make_report(conflicts=[_make_conflict()])
        record_analysis(report, "owner/repo", store=store)

        rows = record_resolution(
            42, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "merged", store=store
        )
        assert rows == 1
        assert store.get_unresolved("owner/repo") == []

    def test_nonexistent_pr(self, store: MetricsStore):
        rows = record_resolution(
            999, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "closed", store=store
        )
        assert rows == 0


class TestComputeDORAMetrics:
    def test_empty_store(self, store: MetricsStore):
        report = compute_dora_metrics("owner/repo", [7], store=store)
        assert len(report.windows) == 1
        w = report.windows[0]
        assert w.merge_count == 0
        assert w.conflict_rate == 0.0
        assert w.unresolved_count == 0

    def test_merge_frequency(self, store: MetricsStore):
        now = datetime.now(UTC)
        for i in range(5):
            report = _make_report(
                pr_number=100 + i,
                conflicts=[_make_conflict(source_pr=100 + i)],
            )
            report.analyzed_at = now - timedelta(days=3)
            record_analysis(report, "owner/repo", store=store)
            record_resolution(
                100 + i,
                "owner/repo",
                now - timedelta(days=2),
                "merged",
                store=store,
            )

        result = compute_dora_metrics("owner/repo", [7], store=store)
        assert result.windows[0].merge_count == 5
        assert result.windows[0].merges_per_day > 0

    def test_conflict_rate(self, store: MetricsStore):
        now = datetime.now(UTC)
        # PR with conflicts
        r1 = _make_report(
            pr_number=42,
            conflicts=[_make_conflict()],
        )
        r1.analyzed_at = now - timedelta(days=1)
        record_analysis(r1, "owner/repo", store=store)

        result = compute_dora_metrics("owner/repo", [7], store=store)
        # 1 PR analyzed, 1 with conflicts => 100% rate
        assert result.windows[0].conflict_rate == 1.0

    def test_resolution_times(self, store: MetricsStore):
        now = datetime.now(UTC)
        r = _make_report(
            pr_number=42,
            conflicts=[_make_conflict()],
        )
        analyzed = now - timedelta(hours=48)
        r.analyzed_at = analyzed
        record_analysis(r, "owner/repo", store=store)
        record_resolution(42, "owner/repo", now, "merged", store=store)

        result = compute_dora_metrics("owner/repo", [7], store=store)
        w = result.windows[0]
        assert w.mean_resolution_time_hours > 0
        assert w.median_resolution_time_hours > 0

    def test_multiple_windows(self, store: MetricsStore):
        result = compute_dora_metrics("owner/repo", [7, 30, 90], store=store)
        assert len(result.windows) == 3
        assert result.windows[0].window_days == 7
        assert result.windows[1].window_days == 30
        assert result.windows[2].window_days == 90

    def test_unresolved_count(self, store: MetricsStore):
        now = datetime.now(UTC)
        r = _make_report(pr_number=42, conflicts=[_make_conflict()])
        r.analyzed_at = now - timedelta(days=1)
        record_analysis(r, "owner/repo", store=store)

        result = compute_dora_metrics("owner/repo", [7], store=store)
        assert result.windows[0].unresolved_count == 1
