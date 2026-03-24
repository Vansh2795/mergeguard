"""Tests for the circuit breaker in the analysis queue."""

from __future__ import annotations

import asyncio

import pytest

from mergeguard.server.events import EventAction, WebhookEvent
from mergeguard.server.queue import AnalysisQueue


def _make_event(
    pr_number: int = 42,
    repo: str = "owner/repo",
) -> WebhookEvent:
    return WebhookEvent(
        platform="github",
        action=EventAction.OPENED,
        repo_full_name=repo,
        pr_number=pr_number,
        head_sha=f"sha-{pr_number}",
        base_branch="main",
        sender="testuser",
    )


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold_failures(self):
        """Circuit opens after _CIRCUIT_THRESHOLD consecutive failures for a repo."""
        call_count = 0

        async def failing_handler(event: WebhookEvent) -> None:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("analysis failed")

        queue = AnalysisQueue(handler=failing_handler, cooldown=0)
        queue._CIRCUIT_THRESHOLD = 3
        queue._CIRCUIT_COOLDOWN = 10.0
        await queue.start()

        # Send enough events to trigger circuit breaker
        for i in range(4):
            await queue.enqueue(_make_event(pr_number=i))
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.3)

        # Circuit should be open for "owner/repo"
        assert "owner/repo" in queue._circuit_open_until
        await queue.stop()

    @pytest.mark.asyncio
    async def test_circuit_skips_events_while_open(self):
        """Events for a repo with open circuit are skipped."""
        processed: list[int] = []
        call_count = 0

        async def handler(event: WebhookEvent) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise RuntimeError("fail")
            processed.append(event.pr_number)

        queue = AnalysisQueue(handler=handler, cooldown=0)
        queue._CIRCUIT_THRESHOLD = 3
        queue._CIRCUIT_COOLDOWN = 60.0  # Long cooldown
        await queue.start()

        # Trigger circuit open
        for i in range(3):
            await queue.enqueue(_make_event(pr_number=i))
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.2)

        # This event should be skipped (circuit is open)
        await queue.enqueue(_make_event(pr_number=99))
        await asyncio.sleep(0.2)

        assert 99 not in processed
        await queue.stop()

    @pytest.mark.asyncio
    async def test_circuit_closes_after_cooldown(self):
        """Circuit closes and resumes processing after cooldown expires."""
        call_count = 0
        processed: list[int] = []

        async def handler(event: WebhookEvent) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise RuntimeError("fail")
            processed.append(event.pr_number)

        queue = AnalysisQueue(handler=handler, cooldown=0)
        queue._CIRCUIT_THRESHOLD = 3
        queue._CIRCUIT_COOLDOWN = 0.2  # Short cooldown for testing
        await queue.start()

        # Trigger circuit open
        for i in range(3):
            await queue.enqueue(_make_event(pr_number=i))
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.2)

        # Circuit should be open
        assert "owner/repo" in queue._circuit_open_until

        # Wait for cooldown to expire
        await asyncio.sleep(0.3)

        # Now this event should be processed (circuit half-open → closed)
        await queue.enqueue(_make_event(pr_number=100))
        await asyncio.sleep(0.2)

        assert 100 in processed
        # Circuit should be closed now (successful processing resets count)
        assert "owner/repo" not in queue._circuit_open_until
        await queue.stop()

    @pytest.mark.asyncio
    async def test_failure_count_resets_on_success(self):
        """A successful handler call resets the failure counter."""
        call_count = 0

        async def intermittent_handler(event: WebhookEvent) -> None:
            nonlocal call_count
            call_count += 1
            # Fail first 2, succeed 3rd, fail 4th and 5th
            if call_count in (1, 2, 4, 5):
                raise RuntimeError("fail")

        queue = AnalysisQueue(handler=intermittent_handler, cooldown=0)
        queue._CIRCUIT_THRESHOLD = 3
        queue._CIRCUIT_COOLDOWN = 60.0
        await queue.start()

        for i in range(5):
            await queue.enqueue(_make_event(pr_number=i))
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.3)

        # Circuit should NOT be open — success at call_count=3 reset the counter,
        # so only 2 consecutive failures after that (not enough for threshold 3)
        assert "owner/repo" not in queue._circuit_open_until
        await queue.stop()

    @pytest.mark.asyncio
    async def test_circuit_is_per_repo(self):
        """Circuit breaker state is tracked per repository."""
        processed: list[str] = []

        async def handler(event: WebhookEvent) -> None:
            if event.repo_full_name == "bad/repo":
                raise RuntimeError("fail")
            processed.append(event.repo_full_name)

        queue = AnalysisQueue(handler=handler, cooldown=0)
        queue._CIRCUIT_THRESHOLD = 2
        queue._CIRCUIT_COOLDOWN = 60.0
        await queue.start()

        # Trip circuit for bad/repo
        for i in range(3):
            await queue.enqueue(_make_event(pr_number=i, repo="bad/repo"))
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.2)

        # good/repo should still work
        await queue.enqueue(_make_event(pr_number=10, repo="good/repo"))
        await asyncio.sleep(0.2)

        assert "good/repo" in processed
        assert "bad/repo" in queue._circuit_open_until
        assert "good/repo" not in queue._circuit_open_until
        await queue.stop()

    @pytest.mark.asyncio
    async def test_drain_timeout_cancels_worker(self):
        """stop() cancels the worker if drain_timeout is exceeded."""
        gate = asyncio.Event()

        async def blocking_handler(event: WebhookEvent) -> None:
            await gate.wait()  # Block forever

        queue = AnalysisQueue(handler=blocking_handler, cooldown=0)
        await queue.start()
        await queue.enqueue(_make_event())
        await asyncio.sleep(0.05)

        # Stop with a very short drain timeout
        await queue.stop(drain_timeout=0.1)

        # Worker should be cancelled
        assert queue._worker_task is not None
        assert queue._worker_task.cancelled() or queue._worker_task.done()
