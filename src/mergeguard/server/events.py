"""Normalized webhook event models.

Converts platform-specific webhook payloads (GitHub, GitLab, Bitbucket) into a
unified WebhookEvent that the analysis pipeline can consume.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class EventAction(StrEnum):
    OPENED = "opened"
    UPDATED = "updated"  # synchronize / push
    CLOSED = "closed"
    REOPENED = "reopened"


class WebhookEvent(BaseModel):
    """Platform-agnostic PR webhook event."""

    platform: str  # "github" | "gitlab" | "bitbucket"
    action: EventAction
    repo_full_name: str  # "owner/repo"
    pr_number: int
    head_sha: str
    base_branch: str
    sender: str  # username that triggered the event


def parse_github_event(headers: dict[str, str], payload: dict[str, Any]) -> WebhookEvent | None:
    """Parse a GitHub webhook payload into a WebhookEvent.

    Returns None for events we don't handle.
    """
    event_type = headers.get("x-github-event", "")
    if event_type != "pull_request":
        return None

    action_map = {
        "opened": EventAction.OPENED,
        "synchronize": EventAction.UPDATED,
        "closed": EventAction.CLOSED,
        "reopened": EventAction.REOPENED,
    }
    raw_action = payload.get("action", "")
    action = action_map.get(raw_action)
    if action is None:
        return None

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    return WebhookEvent(
        platform="github",
        action=action,
        repo_full_name=repo.get("full_name", ""),
        pr_number=pr.get("number", 0),
        head_sha=pr.get("head", {}).get("sha", ""),
        base_branch=pr.get("base", {}).get("ref", ""),
        sender=payload.get("sender", {}).get("login", ""),
    )


def parse_gitlab_event(headers: dict[str, str], payload: dict[str, Any]) -> WebhookEvent | None:
    """Parse a GitLab webhook payload into a WebhookEvent."""
    event_type = headers.get("x-gitlab-event", "")
    if event_type != "Merge Request Hook":
        return None

    attrs = payload.get("object_attributes", {})
    action_map = {
        "open": EventAction.OPENED,
        "update": EventAction.UPDATED,
        "close": EventAction.CLOSED,
        "reopen": EventAction.REOPENED,
        "merge": EventAction.CLOSED,
    }
    action = action_map.get(attrs.get("action", ""))
    if action is None:
        return None

    project = payload.get("project", {})
    return WebhookEvent(
        platform="gitlab",
        action=action,
        repo_full_name=project.get("path_with_namespace", ""),
        pr_number=attrs.get("iid", 0),
        head_sha=attrs.get("last_commit", {}).get("id", ""),
        base_branch=attrs.get("target_branch", ""),
        sender=payload.get("user", {}).get("username", ""),
    )


def parse_bitbucket_event(headers: dict[str, str], payload: dict[str, Any]) -> WebhookEvent | None:
    """Parse a Bitbucket webhook payload into a WebhookEvent."""
    event_key = headers.get("x-event-key", "")
    action_map = {
        "pullrequest:created": EventAction.OPENED,
        "pullrequest:updated": EventAction.UPDATED,
        "pullrequest:fulfilled": EventAction.CLOSED,
        "pullrequest:rejected": EventAction.CLOSED,
    }
    action = action_map.get(event_key)
    if action is None:
        return None

    pr = payload.get("pullrequest", {})
    repo = payload.get("repository", {})
    return WebhookEvent(
        platform="bitbucket",
        action=action,
        repo_full_name=repo.get("full_name", ""),
        pr_number=pr.get("id", 0),
        head_sha=pr.get("source", {}).get("commit", {}).get("hash", ""),
        base_branch=pr.get("destination", {}).get("branch", {}).get("name", ""),
        sender=payload.get("actor", {}).get("username", ""),
    )
