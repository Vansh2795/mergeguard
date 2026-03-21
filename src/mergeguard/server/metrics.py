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
        self.queue_depth = _Counter()  # inc on enqueue, we track total enqueued
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
        ]
        return "\n".join(lines) + "\n"


# Module-level singleton
metrics = Metrics()
