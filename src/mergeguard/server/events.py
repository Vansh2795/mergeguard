"""Normalized webhook event models.

Converts platform-specific webhook payloads (GitHub, GitLab, Bitbucket) into a
unified WebhookEvent that the analysis pipeline can consume.
"""

from __future__ import annotations

import re
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventAction(StrEnum):
    OPENED = "opened"
    UPDATED = "updated"  # synchronize / push
    CLOSED = "closed"
    REOPENED = "reopened"
    MERGE_GROUP_CHECKS_REQUESTED = "merge_group_checks_requested"


def _new_correlation_id() -> str:
    return uuid.uuid4().hex[:12]


class WebhookEvent(BaseModel):
    """Platform-agnostic PR webhook event."""

    platform: str  # "github" | "gitlab" | "bitbucket"
    action: EventAction
    repo_full_name: str  # "owner/repo"
    pr_number: int
    head_sha: str
    base_branch: str
    sender: str  # username that triggered the event
    merged: bool = False  # True if closed via merge
    correlation_id: str = Field(default_factory=_new_correlation_id)


class MergeGroupEvent(BaseModel):
    """GitHub merge_group webhook event."""

    platform: str = "github"
    action: EventAction
    repo_full_name: str
    head_sha: str
    base_branch: str
    sender: str
    pr_numbers: list[int] = Field(default_factory=list)
    correlation_id: str = Field(default_factory=_new_correlation_id)


def _extract_pr_numbers_from_merge_group(payload: dict[str, Any]) -> list[int]:
    """Extract PR numbers from merge group head_ref and head_commit message."""
    pr_numbers: set[int] = set()
    merge_group = payload.get("merge_group", {})

    # Extract from head_ref (e.g., "refs/heads/gh-readonly-queue/main/pr-42-...")
    head_ref = merge_group.get("head_ref", "")
    for match in re.finditer(r"/pr-(\d+)", head_ref):
        pr_numbers.add(int(match.group(1)))

    # Extract from head_commit message (e.g., "Merge pull request #42 ...")
    head_commit = merge_group.get("head_commit", {})
    message = head_commit.get("message", "")
    pr_pattern = r"(?:Merge pull request |PR |pull request )#(\d+)"
    for match in re.finditer(pr_pattern, message, re.IGNORECASE):
        pr_numbers.add(int(match.group(1)))

    return sorted(pr_numbers)


def parse_github_event(
    headers: dict[str, str], payload: dict[str, Any]
) -> WebhookEvent | MergeGroupEvent | None:
    """Parse a GitHub webhook payload into a WebhookEvent or MergeGroupEvent.

    Returns None for events we don't handle.
    """
    event_type = headers.get("x-github-event", "")

    if event_type == "merge_group":
        raw_action = payload.get("action", "")
        if raw_action != "checks_requested":
            return None
        merge_group = payload.get("merge_group")
        if not merge_group:
            return None
        repo = payload.get("repository", {})
        return MergeGroupEvent(
            action=EventAction.MERGE_GROUP_CHECKS_REQUESTED,
            repo_full_name=repo.get("full_name", ""),
            head_sha=merge_group.get("head_sha", ""),
            base_branch=merge_group.get("base_ref", "").removeprefix("refs/heads/"),
            sender=payload.get("sender", {}).get("login", ""),
            pr_numbers=_extract_pr_numbers_from_merge_group(payload),
        )

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
        merged=pr.get("merged", False),
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
        merged=attrs.get("action") == "merge",
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
        merged=event_key == "pullrequest:fulfilled",
    )
