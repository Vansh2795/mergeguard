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

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
)

from mergeguard.server.events import (
    EventAction,
    MergeGroupEvent,
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


def _post_status_safe(
    client: Any,
    sha: str,
    state: str,
    description: str,
    target_url: str = "",
    context: str = "mergeguard/cross-pr-analysis",
) -> None:
    """Safely post a commit status, logging warnings on failure."""
    if not hasattr(client, "post_commit_status"):
        logger.warning("Client %s does not support post_commit_status", type(client).__name__)
        return
    try:
        client.post_commit_status(
            sha=sha,
            state=state,
            description=description,
            target_url=target_url,
            context=context,
        )
        metrics.statuses_posted.inc()
    except Exception:
        metrics.statuses_failed.inc()
        logger.warning("Failed to post commit status on %s", sha, exc_info=True)


def _post_merge_status(
    client: Any,
    report: Any,
    cfg: Any,
) -> None:
    """Post merge readiness status for a single PR report."""
    from mergeguard.core.merge_order import compute_merge_readiness

    readiness = compute_merge_readiness(
        pr_number=report.pr.number,
        reports=[report],
        block_severity=cfg.merge_queue.block_severity,
        priority_labels=cfg.merge_queue.priority_labels,
    )
    _post_status_safe(
        client,
        sha=report.pr.head_sha,
        state=readiness.status_state,
        description=readiness.status_description,
        context=cfg.merge_queue.status_context,
    )


async def _handle_merge_group(
    event: MergeGroupEvent,
    cfg: Any,
    client: Any,
    engine: Any,
) -> None:
    """Handle a merge_group webhook event."""
    metrics.merge_groups_analyzed.inc()

    if not cfg.merge_queue.enabled:
        # Don't block the queue if merge queue integration isn't enabled
        _post_status_safe(
            client,
            sha=event.head_sha,
            state="success",
            description="MergeGuard merge queue not enabled",
            context=cfg.merge_queue.status_context,
        )
        return

    # Post pending status
    _post_status_safe(
        client,
        sha=event.head_sha,
        state="pending",
        description="Analyzing cross-PR conflicts...",
        context=cfg.merge_queue.status_context,
    )

    # Analyze each PR in the merge group
    from mergeguard.core.merge_order import compute_merge_readiness

    any_blocked = False
    all_reports = []
    for pr_num in event.pr_numbers:
        try:
            report = engine.analyze_pr(pr_num)
            all_reports.append(report)
        except Exception:
            logger.warning("Failed to analyze PR #%d in merge group", pr_num, exc_info=True)

    # Check if any PR has blocking conflicts
    block_severity = cfg.merge_queue.block_severity
    for report in all_reports:
        readiness = compute_merge_readiness(
            pr_number=report.pr.number,
            reports=all_reports,
            block_severity=block_severity,
            priority_labels=cfg.merge_queue.priority_labels,
        )
        if readiness.is_blocked:
            any_blocked = True
            break

    if any_blocked:
        _post_status_safe(
            client,
            sha=event.head_sha,
            state="failure",
            description=f"Cross-PR conflicts detected in merge group ({len(event.pr_numbers)} PRs)",
            context=cfg.merge_queue.status_context,
        )
    else:
        _post_status_safe(
            client,
            sha=event.head_sha,
            state="success",
            description=f"No blocking conflicts ({len(event.pr_numbers)} PRs analyzed)",
            context=cfg.merge_queue.status_context,
        )


async def _handle_analysis(event: WebhookEvent | MergeGroupEvent) -> None:
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

    # Route merge group events to dedicated handler
    if isinstance(event, MergeGroupEvent):
        await _handle_merge_group(event, cfg, client, engine)
        return

    if event.action in (EventAction.OPENED, EventAction.UPDATED, EventAction.REOPENED):
        # Post pending status if merge queue is enabled
        if cfg.merge_queue.enabled:
            _post_status_safe(
                client,
                sha=event.head_sha,
                state="pending",
                description="Analyzing cross-PR conflicts...",
                context=cfg.merge_queue.status_context,
            )

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

        # Post merge readiness status after analysis
        if cfg.merge_queue.enabled:
            _post_merge_status(client, report, cfg)

        # Evaluate and execute policy engine actions
        if cfg.policy.enabled:
            from mergeguard.core.policy import evaluate_policies, execute_policy_actions

            evaluation = evaluate_policies(report, cfg.policy)
            if evaluation.actions:
                execute_policy_actions(report, evaluation, client, event.repo_full_name, platform)

        # Record metrics snapshot for DORA tracking
        if cfg.metrics.enabled and report.conflicts:
            from mergeguard.core.metrics import record_analysis

            try:
                record_analysis(report, event.repo_full_name)
            except Exception:
                logger.warning("Failed to record metrics snapshot", exc_info=True)

    elif event.action == EventAction.CLOSED:
        logger.info(
            "PR %s #%d closed — conflict graph will update on next analysis",
            event.repo_full_name,
            event.pr_number,
        )
        if cfg.metrics.enabled:
            from datetime import UTC
            from datetime import datetime as _dt

            from mergeguard.core.metrics import record_resolution

            try:
                resolution_type = "merged" if event.merged else "closed"
                record_resolution(
                    event.pr_number,
                    event.repo_full_name,
                    _dt.now(UTC),
                    resolution_type,
                )
            except Exception:
                logger.warning("Failed to record resolution", exc_info=True)


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

    if isinstance(event, MergeGroupEvent):
        return {"status": "queued", "type": "merge_group", "prs": event.pr_numbers}
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


@app.get("/api/metrics/dora/{owner}/{repo}")
async def dora_metrics(owner: str, repo: str, windows: str = "7,30,90") -> dict[str, Any]:
    """DORA metrics endpoint for a repository."""
    from mergeguard.core.metrics import compute_dora_metrics

    repo_full = f"{owner}/{repo}"
    try:
        time_windows = [int(w.strip()) for w in windows.split(",") if w.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid windows parameter") from None

    if not time_windows:
        time_windows = [7, 30, 90]

    report = compute_dora_metrics(repo_full, time_windows)
    return report.model_dump(mode="json")
