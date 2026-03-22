"""DORA metrics engine — record analysis results and compute metrics."""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime, timedelta

from mergeguard.models import (
    ConflictReport,
    DORAMetrics,
    DORAReport,
    MetricsSnapshot,
)
from mergeguard.storage.metrics_store import MetricsStore

_DEFAULT_DB = ".mergeguard-cache/decisions.db"


def _get_store(store: MetricsStore | None) -> MetricsStore:
    if store is not None:
        return store
    return MetricsStore(_DEFAULT_DB)


def _severity_max(report: ConflictReport) -> str:
    """Extract the highest severity from a conflict report."""
    order = {"critical": 3, "warning": 2, "info": 1}
    best = "none"
    best_rank = 0
    for c in report.conflicts:
        rank = order.get(c.severity.value, 0)
        if rank > best_rank:
            best_rank = rank
            best = c.severity.value
    return best


def _percentile(values: list[float], p: float) -> float:
    """Compute the p-th percentile (0-100) of a sorted list."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (p / 100.0) * (len(sorted_vals) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def record_analysis(
    report: ConflictReport,
    repo: str,
    store: MetricsStore | None = None,
) -> None:
    """Record a conflict analysis result as a metrics snapshot.

    Called after every analyze_pr() that finds conflicts.
    """
    if not report.conflicts:
        return

    own_store = store is None
    s = _get_store(store)
    try:
        snapshot = MetricsSnapshot(
            pr_number=report.pr.number,
            repo=repo,
            analyzed_at=report.analyzed_at,
            risk_score=report.risk_score,
            conflict_count=len(report.conflicts),
            severity_max=_severity_max(report),
        )
        s.record_snapshot(snapshot)
    finally:
        if own_store:
            s.close()


def record_resolution(
    pr_number: int,
    repo: str,
    resolved_at: datetime,
    resolution_type: str,
    store: MetricsStore | None = None,
) -> int:
    """Mark all unresolved snapshots for a PR as resolved. Returns rows affected."""
    own_store = store is None
    s = _get_store(store)
    try:
        return s.resolve_pr(pr_number, repo, resolved_at, resolution_type)
    finally:
        if own_store:
            s.close()


def compute_dora_metrics(
    repo: str,
    time_windows: list[int] | None = None,
    store: MetricsStore | None = None,
) -> DORAReport:
    """Compute DORA metrics for the given repo across time windows."""
    if time_windows is None:
        time_windows = [7, 30, 90]

    own_store = store is None
    s = _get_store(store)
    try:
        now = datetime.now(UTC)
        windows: list[DORAMetrics] = []

        for days in time_windows:
            period_start = now - timedelta(days=days)
            snapshots = s.get_snapshots(repo, period_start, now)
            unresolved = s.get_unresolved(repo)
            merge_count = s.get_merge_count(repo, period_start)

            # Distinct PRs analyzed in this window
            analyzed_prs = {snap.pr_number for snap in snapshots}
            prs_with_conflicts = {snap.pr_number for snap in snapshots if snap.conflict_count > 0}
            total_analyzed = len(analyzed_prs)
            conflict_count = len(prs_with_conflicts)
            conflict_rate = conflict_count / total_analyzed if total_analyzed > 0 else 0.0

            # Resolution times (only for resolved snapshots in this window)
            resolution_times: list[float] = []
            for snap in snapshots:
                if snap.resolved_at is not None:
                    delta = (snap.resolved_at - snap.analyzed_at).total_seconds() / 3600.0
                    if delta >= 0:
                        resolution_times.append(delta)

            mean_res = statistics.mean(resolution_times) if resolution_times else 0.0
            median_res = statistics.median(resolution_times) if resolution_times else 0.0
            p90_res = _percentile(resolution_times, 90)

            # MTTRC = mean time to resolve conflicts (same as mean, but semantically distinct)
            mttrc = mean_res

            merges_per_day = merge_count / days if days > 0 else 0.0

            windows.append(
                DORAMetrics(
                    window_days=days,
                    period_start=period_start,
                    period_end=now,
                    merge_count=merge_count,
                    merges_per_day=round(merges_per_day, 2),
                    total_prs_analyzed=total_analyzed,
                    prs_with_conflicts=conflict_count,
                    conflict_rate=round(conflict_rate, 4),
                    resolution_times_hours=resolution_times,
                    mean_resolution_time_hours=round(mean_res, 2),
                    median_resolution_time_hours=round(median_res, 2),
                    p90_resolution_time_hours=round(p90_res, 2),
                    mttrc_hours=round(mttrc, 2),
                    unresolved_count=len(unresolved),
                )
            )

        return DORAReport(
            repo=repo,
            generated_at=now,
            windows=windows,
        )
    finally:
        if own_store:
            s.close()
