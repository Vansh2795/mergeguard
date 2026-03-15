"""Slack and Teams webhook notifications for MergeGuard."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from mergeguard.models import ConflictReport

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI = {
    "critical": ":red_circle:",
    "warning": ":warning:",
    "info": ":information_source:",
}


def notify_slack(
    webhook_url: str,
    report: ConflictReport,
    repo: str,
    notify_on: list[str] | None = None,
) -> bool:
    """Post conflict summary to Slack via incoming webhook (Block Kit).

    Args:
        webhook_url: Slack incoming webhook URL.
        report: Analysis report to summarize.
        repo: Repository name for display.
        notify_on: Severity levels to notify on (default: ["critical", "warning"]).

    Returns:
        True if notification was sent successfully.
    """
    if notify_on is None:
        notify_on = ["critical", "warning"]

    # Filter conflicts to matching severities
    matching = [c for c in report.conflicts if c.severity.value in notify_on]
    if not matching:
        return False

    severity_counts = {}
    for c in matching:
        severity_counts[c.severity.value] = severity_counts.get(c.severity.value, 0) + 1

    # Build Block Kit payload
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"MergeGuard: PR #{report.pr.number}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{report.pr.title}* ({repo})\n"
                    f"Risk Score: *{report.risk_score:.0f}/100* | "
                    f"{len(matching)} conflict(s)"
                ),
            },
        },
    ]

    # Add severity summary
    summary_parts = []
    for sev in ["critical", "warning", "info"]:
        count = severity_counts.get(sev, 0)
        if count > 0:
            emoji = _SEVERITY_EMOJI.get(sev, "")
            summary_parts.append(f"{emoji} {count} {sev}")

    if summary_parts:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": " | ".join(summary_parts)},
            }
        )

    # Top conflicts (max 5)
    conflict_lines = []
    for c in matching[:5]:
        emoji = _SEVERITY_EMOJI.get(c.severity.value, "")
        symbol = f" `{c.symbol_name}`" if c.symbol_name else ""
        conflict_lines.append(
            f"{emoji} *{c.conflict_type.value}* with #{c.target_pr}: `{c.file_path}`{symbol}"
        )

    if conflict_lines:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(conflict_lines)},
            }
        )

    if len(matching) > 5:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_...and {len(matching) - 5} more conflict(s)_",
                    }
                ],
            }
        )

    payload = {"blocks": blocks}

    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10.0)
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.warning("Failed to send Slack notification", exc_info=True)
        return False


def notify_teams(
    webhook_url: str,
    report: ConflictReport,
    repo: str,
    notify_on: list[str] | None = None,
) -> bool:
    """Post conflict summary to Microsoft Teams via incoming webhook (Adaptive Cards).

    Args:
        webhook_url: Teams incoming webhook URL.
        report: Analysis report to summarize.
        repo: Repository name for display.
        notify_on: Severity levels to notify on (default: ["critical", "warning"]).

    Returns:
        True if notification was sent successfully.
    """
    if notify_on is None:
        notify_on = ["critical", "warning"]

    matching = [c for c in report.conflicts if c.severity.value in notify_on]
    if not matching:
        return False

    severity_counts = {}
    for c in matching:
        severity_counts[c.severity.value] = severity_counts.get(c.severity.value, 0) + 1

    # Build Adaptive Card
    facts = []
    for sev in ["critical", "warning", "info"]:
        count = severity_counts.get(sev, 0)
        if count > 0:
            facts.append({"title": sev.title(), "value": str(count)})

    conflict_items = []
    for c in matching[:5]:
        symbol = f" ({c.symbol_name})" if c.symbol_name else ""
        conflict_items.append(
            {
                "type": "TextBlock",
                "text": (
                    f"**{c.severity.value.upper()}** {c.conflict_type.value} "
                    f"with #{c.target_pr}: `{c.file_path}`{symbol}"
                ),
                "wrap": True,
                "size": "Small",
            }
        )

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"MergeGuard: PR #{report.pr.number}",
                            "weight": "Bolder",
                            "size": "Large",
                        },
                        {
                            "type": "TextBlock",
                            "text": f"{report.pr.title} ({repo})",
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Risk Score", "value": f"{report.risk_score:.0f}/100"},
                                {"title": "Conflicts", "value": str(len(matching))},
                                *facts,
                            ],
                        },
                        *conflict_items,
                    ],
                },
            }
        ],
    }

    try:
        resp = httpx.post(webhook_url, json=card, timeout=10.0)
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.warning("Failed to send Teams notification", exc_info=True)
        return False
