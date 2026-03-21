"""FastAPI webhook server for real-time conflict detection.

Routes:
- POST /webhooks/github   — GitHub webhook receiver
- POST /webhooks/gitlab   — GitLab webhook receiver
- POST /webhooks/bitbucket — Bitbucket webhook receiver
- GET  /health            — Health check
- GET  /metrics           — Prometheus metrics
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request, Response

from mergeguard.server.events import (
    EventAction,
    WebhookEvent,
    parse_bitbucket_event,
    parse_github_event,
    parse_gitlab_event,
)
from mergeguard.server.metrics import metrics
from mergeguard.server.queue import AnalysisQueue

logger = logging.getLogger(__name__)

_queue: AnalysisQueue | None = None
_start_time: float = 0.0


async def _handle_analysis(event: WebhookEvent) -> None:
    """Run MergeGuard analysis for a webhook event.

    Called by the queue worker in the background.
    """
    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    cfg = load_config()
    platform = event.platform
    token = _get_token_for_platform(platform)
    if not token:
        logger.error("No token configured for platform %s", platform)
        return

    client = _create_client_for_event(platform, token, event.repo_full_name)

    engine = MergeGuardEngine(config=cfg, client=client)

    if event.action in (EventAction.OPENED, EventAction.UPDATED, EventAction.REOPENED):
        report = engine.analyze_pr(event.pr_number)

        if report.conflicts:
            from mergeguard.output.github_comment import format_report
            from mergeguard.output.inline_annotations import (
                format_review_comments,
                format_review_summary,
            )

            review_comments = []
            if cfg.inline_annotations:
                review_comments = format_review_comments(
                    report, event.repo_full_name, platform=platform
                )

            markdown = format_report(
                report,
                event.repo_full_name,
                platform=platform,
                inline_count=len(review_comments),
            )
            client.post_pr_comment(event.pr_number, markdown)

            if review_comments:
                review_body = format_review_summary(report, len(review_comments))
                try:
                    client.post_pr_review(event.pr_number, review_body, review_comments)
                except Exception:
                    logger.warning(
                        "Failed to post inline annotations for %s #%d",
                        event.repo_full_name,
                        event.pr_number,
                        exc_info=True,
                    )

    elif event.action == EventAction.CLOSED:
        logger.info(
            "PR %s #%d closed — conflict graph will update on next analysis",
            event.repo_full_name,
            event.pr_number,
        )


def _get_token_for_platform(platform: str) -> str | None:
    """Get the API token for a platform from environment variables."""
    env_map = {
        "github": "GITHUB_TOKEN",
        "gitlab": "GITLAB_TOKEN",
        "bitbucket": "BITBUCKET_APP_PASSWORD",
    }
    return os.environ.get(env_map.get(platform, ""))


def _create_client_for_event(platform: str, token: str, repo: str) -> Any:
    """Create an SCM client for the given platform."""
    if platform == "gitlab":
        from mergeguard.integrations.gitlab_client import GitLabClient

        gitlab_url = os.environ.get("GITLAB_URL", "https://gitlab.com")
        return GitLabClient(token, repo, gitlab_url)
    elif platform == "bitbucket":
        from mergeguard.integrations.bitbucket_client import BitbucketClient

        return BitbucketClient(token, repo)
    else:
        from mergeguard.integrations.github_client import GitHubClient

        github_url = os.environ.get("MERGEGUARD_GITHUB_URL")
        return GitHubClient(token, repo, base_url=github_url)


# ── Signature verification ──────────────────────────────────────────


def verify_github_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_gitlab_token(token: str | None, secret: str) -> bool:
    """Verify GitLab webhook secret token."""
    if not token:
        return False
    return hmac.compare_digest(token, secret)


def verify_bitbucket_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    """Verify Bitbucket HMAC-SHA256 webhook signature (same scheme as GitHub)."""
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── FastAPI app ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start/stop the analysis queue with the server lifecycle."""
    global _queue, _start_time
    _start_time = time.monotonic()
    _queue = AnalysisQueue(handler=_handle_analysis)
    await _queue.start()
    yield
    await _queue.stop()


app = FastAPI(
    title="MergeGuard Webhook Server",
    description="Real-time cross-PR conflict detection via webhooks",
    version="0.5.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    uptime = time.monotonic() - _start_time
    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 1),
        "queue_pending": _queue.pending_count if _queue else 0,
        "analyses_completed": metrics.analyses_completed.value,
        "analyses_failed": metrics.analyses_failed.value,
    }


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=metrics.render(), media_type="text/plain; charset=utf-8")


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
) -> dict[str, Any]:
    """Receive GitHub webhook events."""
    body = await request.body()
    metrics.webhooks_received.inc()

    secret = os.environ.get("MERGEGUARD_WEBHOOK_SECRET_GITHUB", "")
    if secret and not verify_github_signature(body, x_hub_signature_256, secret):
        metrics.webhooks_invalid.inc()
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    headers = {"x-github-event": x_github_event or ""}
    event = parse_github_event(headers, payload)

    if event is None:
        return {"status": "ignored"}

    assert _queue is not None
    await _queue.enqueue(event)
    return {"status": "queued", "pr": event.pr_number}


@app.post("/webhooks/gitlab")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str | None = Header(None),
    x_gitlab_event: str | None = Header(None),
) -> dict[str, Any]:
    """Receive GitLab webhook events."""
    metrics.webhooks_received.inc()

    secret = os.environ.get("MERGEGUARD_WEBHOOK_SECRET_GITLAB", "")
    if secret and not verify_gitlab_token(x_gitlab_token, secret):
        metrics.webhooks_invalid.inc()
        raise HTTPException(status_code=401, detail="Invalid token")

    payload = await request.json()
    headers = {"x-gitlab-event": x_gitlab_event or ""}
    event = parse_gitlab_event(headers, payload)

    if event is None:
        return {"status": "ignored"}

    assert _queue is not None
    await _queue.enqueue(event)
    return {"status": "queued", "pr": event.pr_number}


@app.post("/webhooks/bitbucket")
async def bitbucket_webhook(
    request: Request,
    x_hub_signature: str | None = Header(None),
    x_event_key: str | None = Header(None),
) -> dict[str, Any]:
    """Receive Bitbucket webhook events."""
    body = await request.body()
    metrics.webhooks_received.inc()

    secret = os.environ.get("MERGEGUARD_WEBHOOK_SECRET_BITBUCKET", "")
    if secret and not verify_bitbucket_signature(body, x_hub_signature, secret):
        metrics.webhooks_invalid.inc()
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    headers = {"x-event-key": x_event_key or ""}
    event = parse_bitbucket_event(headers, payload)

    if event is None:
        return {"status": "ignored"}

    assert _queue is not None
    await _queue.enqueue(event)
    return {"status": "queued", "pr": event.pr_number}
