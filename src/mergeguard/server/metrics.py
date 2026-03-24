"""Prometheus metrics for the MergeGuard webhook server.

Lightweight implementation using plain counters/histograms — no dependency on
prometheus_client. The /metrics endpoint renders Prometheus text format directly.
"""

from __future__ import annotations

import threading
import time


class _Counter:
    __slots__ = ("_value", "_lock")

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def inc(self, amount: int = 1) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> int:
        return self._value


class _Gauge:
    __slots__ = ("_value", "_lock")

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def inc(self, amount: int = 1) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: int = 1) -> None:
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> int:
        return self._value


class _Histogram:
    """Simple histogram that tracks count and sum (no buckets)."""

    __slots__ = ("_count", "_sum", "_lock")

    def __init__(self) -> None:
        self._count = 0
        self._sum = 0.0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._count += 1
            self._sum += value

    @property
    def count(self) -> int:
        return self._count

    @property
    def total(self) -> float:
        return self._sum


class Metrics:
    """Singleton metrics registry for the webhook server."""

    def __init__(self) -> None:
        self.webhooks_received = _Counter()
        self.webhooks_invalid = _Counter()
        self.analyses_started = _Counter()
        self.analyses_completed = _Counter()
        self.analyses_failed = _Counter()
        self.analysis_duration = _Histogram()
        self.queue_depth = _Gauge()  # inc on enqueue, dec after task_done
        self.statuses_posted = _Counter()
        self.statuses_failed = _Counter()
        self.merge_groups_analyzed = _Counter()
        self._start_time = time.monotonic()

    def render(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        uptime = time.monotonic() - self._start_time
        lines = [
            "# HELP mergeguard_uptime_seconds Server uptime in seconds.",
            "# TYPE mergeguard_uptime_seconds gauge",
            f"mergeguard_uptime_seconds {uptime:.1f}",
            "",
            "# HELP mergeguard_webhooks_received_total Total webhooks received.",
            "# TYPE mergeguard_webhooks_received_total counter",
            f"mergeguard_webhooks_received_total {self.webhooks_received.value}",
            "",
            "# HELP mergeguard_webhooks_invalid_total Webhooks rejected (bad sig).",
            "# TYPE mergeguard_webhooks_invalid_total counter",
            f"mergeguard_webhooks_invalid_total {self.webhooks_invalid.value}",
            "",
            "# HELP mergeguard_analyses_started_total Analyses enqueued.",
            "# TYPE mergeguard_analyses_started_total counter",
            f"mergeguard_analyses_started_total {self.analyses_started.value}",
            "",
            "# HELP mergeguard_analyses_completed_total Analyses completed successfully.",
            "# TYPE mergeguard_analyses_completed_total counter",
            f"mergeguard_analyses_completed_total {self.analyses_completed.value}",
            "",
            "# HELP mergeguard_analyses_failed_total Analyses that failed.",
            "# TYPE mergeguard_analyses_failed_total counter",
            f"mergeguard_analyses_failed_total {self.analyses_failed.value}",
            "",
            "# HELP mergeguard_analysis_duration_seconds Analysis duration.",
            "# TYPE mergeguard_analysis_duration_seconds summary",
            f"mergeguard_analysis_duration_seconds_count {self.analysis_duration.count}",
            f"mergeguard_analysis_duration_seconds_sum {self.analysis_duration.total:.3f}",
            "",
            "# HELP mergeguard_queue_depth Current queue depth.",
            "# TYPE mergeguard_queue_depth gauge",
            f"mergeguard_queue_depth {self.queue_depth.value}",
            "",
            "# HELP mergeguard_statuses_posted_total Commit statuses posted.",
            "# TYPE mergeguard_statuses_posted_total counter",
            f"mergeguard_statuses_posted_total {self.statuses_posted.value}",
            "",
            "# HELP mergeguard_statuses_failed_total Commit status post failures.",
            "# TYPE mergeguard_statuses_failed_total counter",
            f"mergeguard_statuses_failed_total {self.statuses_failed.value}",
            "",
            "# HELP mergeguard_merge_groups_analyzed_total Merge groups analyzed.",
            "# TYPE mergeguard_merge_groups_analyzed_total counter",
            f"mergeguard_merge_groups_analyzed_total {self.merge_groups_analyzed.value}",
            "",
        ]
        return "\n".join(lines) + "\n"


# Module-level singleton
metrics = Metrics()
