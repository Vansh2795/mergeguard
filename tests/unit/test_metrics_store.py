"""Tests for MetricsStore — SQLite-backed DORA metrics storage."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mergeguard.models import MetricsSnapshot
from mergeguard.storage.metrics_store import MetricsStore


@pytest.fixture
def store():
    """In-memory SQLite store for testing."""
    s = MetricsStore(":memory:")
    yield s
    s.close()


def _make_snapshot(
    pr_number: int = 42,
    repo: str = "owner/repo",
    risk_score: float = 75.0,
    conflict_count: int = 3,
    severity_max: str = "critical",
    analyzed_at: datetime | None = None,
    resolved_at: datetime | None = None,
    resolution_type: str | None = None,
) -> MetricsSnapshot:
    return MetricsSnapshot(
        pr_number=pr_number,
        repo=repo,
        analyzed_at=analyzed_at or datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC),
        risk_score=risk_score,
        conflict_count=conflict_count,
        severity_max=severity_max,
        resolved_at=resolved_at,
        resolution_type=resolution_type,
    )


class TestRecordSnapshot:
    def test_insert_new(self, store: MetricsStore):
        snap = _make_snapshot()
        store.record_snapshot(snap)
        results = store.get_snapshots("owner/repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(results) == 1
        assert results[0].pr_number == 42
        assert results[0].risk_score == 75.0

    def test_upsert_updates_existing_unresolved(self, store: MetricsStore):
        snap1 = _make_snapshot(risk_score=50.0)
        store.record_snapshot(snap1)

        snap2 = _make_snapshot(
            risk_score=80.0,
            conflict_count=5,
            analyzed_at=datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC),
        )
        store.record_snapshot(snap2)

        results = store.get_snapshots("owner/repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(results) == 1
        assert results[0].risk_score == 80.0
        assert results[0].conflict_count == 5

    def test_insert_new_after_resolved(self, store: MetricsStore):
        snap1 = _make_snapshot()
        store.record_snapshot(snap1)
        store.resolve_pr(42, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "merged")

        snap2 = _make_snapshot(
            analyzed_at=datetime(2026, 3, 17, 10, 0, 0, tzinfo=UTC),
        )
        store.record_snapshot(snap2)

        results = store.get_snapshots("owner/repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(results) == 2


class TestResolvePR:
    def test_resolve_marks_resolved(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot())
        rows = store.resolve_pr(
            42, "owner/repo", datetime(2026, 3, 16, 12, 0, 0, tzinfo=UTC), "merged"
        )
        assert rows == 1

        unresolved = store.get_unresolved("owner/repo")
        assert len(unresolved) == 0

    def test_resolve_nonexistent_returns_zero(self, store: MetricsStore):
        rows = store.resolve_pr(999, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "closed")
        assert rows == 0

    def test_resolve_only_affects_matching_pr(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot(pr_number=42))
        store.record_snapshot(_make_snapshot(pr_number=43))
        store.resolve_pr(42, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "merged")

        unresolved = store.get_unresolved("owner/repo")
        assert len(unresolved) == 1
        assert unresolved[0].pr_number == 43


class TestGetSnapshots:
    def test_filters_by_time_window(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot(analyzed_at=datetime(2026, 3, 1, tzinfo=UTC)))
        store.record_snapshot(
            _make_snapshot(pr_number=43, analyzed_at=datetime(2026, 3, 20, tzinfo=UTC))
        )

        results = store.get_snapshots(
            "owner/repo",
            datetime(2026, 3, 10, tzinfo=UTC),
            datetime(2026, 3, 25, tzinfo=UTC),
        )
        assert len(results) == 1
        assert results[0].pr_number == 43

    def test_filters_by_repo(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot(repo="owner/repo"))
        store.record_snapshot(_make_snapshot(pr_number=99, repo="other/repo"))

        results = store.get_snapshots("owner/repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(results) == 1
        assert results[0].pr_number == 42


class TestGetUnresolved:
    def test_returns_only_unresolved(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot(pr_number=42))
        store.record_snapshot(_make_snapshot(pr_number=43))
        store.resolve_pr(42, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "merged")

        unresolved = store.get_unresolved("owner/repo")
        assert len(unresolved) == 1
        assert unresolved[0].pr_number == 43

    def test_empty_when_all_resolved(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot())
        store.resolve_pr(42, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "merged")
        assert store.get_unresolved("owner/repo") == []


class TestGetMergeCount:
    def test_counts_distinct_merged_prs(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot(pr_number=42))
        store.record_snapshot(_make_snapshot(pr_number=43))
        store.resolve_pr(42, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "merged")
        store.resolve_pr(43, "owner/repo", datetime(2026, 3, 17, tzinfo=UTC), "merged")

        count = store.get_merge_count("owner/repo", datetime(2026, 3, 1, tzinfo=UTC))
        assert count == 2

    def test_excludes_closed_not_merged(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot(pr_number=42))
        store.resolve_pr(42, "owner/repo", datetime(2026, 3, 16, tzinfo=UTC), "closed")

        count = store.get_merge_count("owner/repo", datetime(2026, 3, 1, tzinfo=UTC))
        assert count == 0

    def test_respects_since_filter(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot(pr_number=42))
        store.resolve_pr(42, "owner/repo", datetime(2026, 3, 5, tzinfo=UTC), "merged")

        count = store.get_merge_count("owner/repo", datetime(2026, 3, 10, tzinfo=UTC))
        assert count == 0


class TestPrune:
    def test_deletes_old_resolved(self, store: MetricsStore):
        snap = _make_snapshot(
            analyzed_at=datetime(2025, 1, 1, tzinfo=UTC),
            resolved_at=datetime(2025, 1, 2, tzinfo=UTC),
            resolution_type="merged",
        )
        store.record_snapshot(snap)

        deleted = store.prune(retention_days=30)
        assert deleted == 1

        results = store.get_snapshots("owner/repo", datetime(2024, 1, 1, tzinfo=UTC))
        assert len(results) == 0

    def test_keeps_unresolved(self, store: MetricsStore):
        store.record_snapshot(_make_snapshot())
        deleted = store.prune(retention_days=1)
        assert deleted == 0

        results = store.get_snapshots("owner/repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(results) == 1
