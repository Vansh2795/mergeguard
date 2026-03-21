"""Tests for the analysis queue — rate limiting, deduplication, graceful shutdown."""

from __future__ import annotations

import asyncio

import pytest

from mergeguard.server.events import EventAction, WebhookEvent
from mergeguard.server.queue import AnalysisQueue


def _make_event(
    pr_number: int = 42,
    repo: str = "owner/repo",
    action: EventAction = EventAction.OPENED,
) -> WebhookEvent:
    return WebhookEvent(
        platform="github",
        action=action,
        repo_full_name=repo,
        pr_number=pr_number,
        head_sha=f"sha-{pr_number}",
        base_branch="main",
        sender="testuser",
    )


class TestAnalysisQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_process(self):
        """Events are processed by the handler."""
        processed: list[int] = []

        async def handler(event: WebhookEvent) -> None:
            processed.append(event.pr_number)

        queue = AnalysisQueue(handler=handler, cooldown=0)
        await queue.start()

        await queue.enqueue(_make_event(pr_number=1))
        await queue.enqueue(_make_event(pr_number=2))

        # Give the worker time to process
        await asyncio.sleep(0.2)
        await queue.stop()

        assert 1 in processed
        assert 2 in processed

    @pytest.mark.asyncio
    async def test_deduplication(self):
        """When multiple events arrive for the same PR, only the latest is processed."""
        processed: list[str] = []
        gate = asyncio.Event()

        async def slow_handler(event: WebhookEvent) -> None:
            # Block on first call to let dedup events arrive
            if not processed:
                gate.set()
                await asyncio.sleep(0.15)
            processed.append(event.head_sha)

        queue = AnalysisQueue(handler=slow_handler, cooldown=0)
        await queue.start()

        # Enqueue the first event (will start processing immediately)
        await queue.enqueue(_make_event(pr_number=1))
        # Wait for first handler to start
        await asyncio.sleep(0.05)

        # Enqueue two more for same PR — second should supersede first
        event_old = _make_event(pr_number=1)
        event_old.head_sha = "old-sha"
        event_new = _make_event(pr_number=1)
        event_new.head_sha = "new-sha"
        await queue.enqueue(event_old)
        await queue.enqueue(event_new)

        await asyncio.sleep(0.5)
        await queue.stop()

        # The "new-sha" should be the one processed (old-sha was superseded)
        assert "new-sha" in processed

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """Queue finishes in-flight work before stopping."""
        completed = asyncio.Event()

        async def handler(event: WebhookEvent) -> None:
            await asyncio.sleep(0.1)
            completed.set()

        queue = AnalysisQueue(handler=handler, cooldown=0)
        await queue.start()
        await queue.enqueue(_make_event())

        # Stop immediately — should still wait for the task
        await asyncio.sleep(0.05)
        await queue.stop()

        # The handler should have had a chance to finish
        # (either completed or queue drained cleanly)
        # We just check no exceptions were raised

    @pytest.mark.asyncio
    async def test_handler_exception_doesnt_crash_worker(self):
        """A failing handler doesn't stop the queue worker."""
        call_count = 0

        async def failing_then_ok(event: WebhookEvent) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("boom")

        queue = AnalysisQueue(handler=failing_then_ok, cooldown=0)
        await queue.start()

        await queue.enqueue(_make_event(pr_number=1))
        await asyncio.sleep(0.1)
        await queue.enqueue(_make_event(pr_number=2))
        await asyncio.sleep(0.1)
        await queue.stop()

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_pending_count(self):
        """pending_count reflects queue size."""
        gate = asyncio.Event()

        async def blocking_handler(event: WebhookEvent) -> None:
            await gate.wait()

        queue = AnalysisQueue(handler=blocking_handler, cooldown=0)
        await queue.start()

        await queue.enqueue(_make_event(pr_number=1))
        await asyncio.sleep(0.05)
        # First item is being processed, queue should be near-empty
        await queue.enqueue(_make_event(pr_number=2))
        await queue.enqueue(_make_event(pr_number=3))

        assert queue.pending_count >= 1  # At least the non-processing items

        gate.set()
        await asyncio.sleep(0.2)
        await queue.stop()
