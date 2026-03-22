"""Background task queue for webhook-triggered analysis.

Uses asyncio for the default in-process queue. Designed with a clean interface
so a Redis/Celery adapter can be swapped in for production scale.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mergeguard.server.events import MergeGroupEvent, WebhookEvent

from mergeguard.server.metrics import metrics

logger = logging.getLogger(__name__)

# Minimum seconds between analyses for the same repo (rate limiting)
_DEFAULT_COOLDOWN = 5.0


@dataclass
class AnalysisTask:
    """A queued analysis job."""

    event: WebhookEvent | MergeGroupEvent
    enqueued_at: float = field(default_factory=time.monotonic)


class AnalysisQueue:
    """Async in-process queue with per-repo rate limiting.

    - Deduplicates: if a newer event arrives for the same PR before the previous
      one is processed, the older one is replaced.
    - Rate limits: at most one analysis per repo every `cooldown` seconds.
    - Graceful shutdown: finishes in-flight tasks before stopping.
    """

    def __init__(
        self,
        handler: object,  # callable(WebhookEvent) -> awaitable
        cooldown: float = _DEFAULT_COOLDOWN,
        max_size: int = 1000,
    ) -> None:
        self._queue: asyncio.Queue[AnalysisTask | None] = asyncio.Queue(maxsize=max_size)
        self._handler = handler
        self._cooldown = cooldown
        self._last_run: dict[str, float] = defaultdict(float)
        self._pending: dict[str, AnalysisTask] = {}  # repo:pr -> latest task
        self._worker_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._shutting_down = False

    async def start(self) -> None:
        """Start the background worker."""
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Analysis queue worker started")

    async def stop(self) -> None:
        """Signal shutdown and wait for in-flight work to finish."""
        self._shutting_down = True
        await self._queue.put(None)  # Sentinel to wake the worker
        if self._worker_task is not None:
            await self._worker_task
        logger.info("Analysis queue worker stopped")

    async def enqueue(self, event: WebhookEvent | MergeGroupEvent) -> None:
        """Add an analysis task to the queue.

        Deduplicates by replacing pending tasks for the same PR or merge group.
        """
        from mergeguard.server.events import MergeGroupEvent

        if isinstance(event, MergeGroupEvent):
            key = f"{event.repo_full_name}:merge_group:{event.head_sha}"
        else:
            key = f"{event.repo_full_name}:{event.pr_number}"
        task = AnalysisTask(event=event)
        self._pending[key] = task
        metrics.queue_depth.inc()
        await self._queue.put(task)

    async def _worker(self) -> None:
        """Process queued analysis tasks."""
        while True:
            task = await self._queue.get()
            if task is None:
                # Sentinel — finish remaining items then exit
                break

            event = task.event
            from mergeguard.server.events import MergeGroupEvent

            if isinstance(event, MergeGroupEvent):
                key = f"{event.repo_full_name}:merge_group:{event.head_sha}"
            else:
                key = f"{event.repo_full_name}:{event.pr_number}"

            # Skip if a newer task has superseded this one
            if self._pending.get(key) is not task:
                self._queue.task_done()
                continue

            # Rate limit per repo
            repo = event.repo_full_name
            elapsed = time.monotonic() - self._last_run[repo]
            if elapsed < self._cooldown:
                await asyncio.sleep(self._cooldown - elapsed)

            self._last_run[repo] = time.monotonic()
            del self._pending[key]

            metrics.analyses_started.inc()
            start = time.monotonic()
            try:
                await self._handler(event)  # type: ignore[operator]
                duration = time.monotonic() - start
                metrics.analysis_duration.observe(duration)
                metrics.analyses_completed.inc()
                event_label = (
                    f"merge_group:{event.head_sha[:8]}"
                    if isinstance(event, MergeGroupEvent)
                    else f"#{event.pr_number}"
                )
                logger.info(
                    "Analysis completed for %s %s in %.1fs",
                    event.repo_full_name,
                    event_label,
                    duration,
                )
            except Exception:
                metrics.analyses_failed.inc()
                event_label = (
                    f"merge_group:{event.head_sha[:8]}"
                    if isinstance(event, MergeGroupEvent)
                    else f"#{event.pr_number}"
                )
                logger.exception(
                    "Analysis failed for %s %s",
                    event.repo_full_name,
                    event_label,
                )
            finally:
                self._queue.task_done()

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()
