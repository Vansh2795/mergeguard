"""Tests for Slack/Teams notification formatting and SSRF validation."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import httpx
import pytest

from mergeguard.models import (
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    PRInfo,
)
from mergeguard.output.notifications import (
    _validate_webhook_url,
    notify_slack,
    notify_slack_per_team,
    notify_teams,
)


def _make_pr(number: int = 42) -> PRInfo:
    return PRInfo(
        number=number,
        title="Add auth module",
        author="alice",
        base_branch="main",
        head_branch="feature/auth",
        head_sha="abc123",
        created_at=datetime(2026, 1, 15),
        updated_at=datetime(2026, 1, 16),
    )


def _make_conflict(
    severity: ConflictSeverity = ConflictSeverity.CRITICAL,
    conflict_type: ConflictType = ConflictType.HARD,
    target_pr: int = 43,
    symbol_name: str | None = "get_user",
    owners: list[str] | None = None,
) -> Conflict:
    return Conflict(
        conflict_type=conflict_type,
        severity=severity,
        source_pr=42,
        target_pr=target_pr,
        file_path="src/auth.py",
        symbol_name=symbol_name,
        description="Overlapping changes",
        recommendation="Coordinate",
        owners=owners or [],
    )


def _make_report(
    conflicts: list[Conflict] | None = None,
    risk_score: float = 75.0,
) -> ConflictReport:
    return ConflictReport(
        pr=_make_pr(),
        conflicts=conflicts or [_make_conflict()],
        risk_score=risk_score,
        analysis_duration_ms=500,
    )


def _ok_response() -> httpx.Response:
    """Build a 200 response that supports raise_for_status()."""
    return httpx.Response(200, request=httpx.Request("POST", "https://example.com"))


# ── SSRF Validation ──


class TestValidateWebhookUrl:
    def test_rejects_http(self):
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_webhook_url("http://hooks.slack.com/services/T/B/X")

    def test_accepts_https(self):
        # Should not raise
        _validate_webhook_url("https://hooks.slack.com/services/T/B/X")

    def test_rejects_private_ipv4_10(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://10.0.0.1/hook")

    def test_rejects_private_ipv4_172(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://172.16.0.1/hook")

    def test_rejects_private_ipv4_192(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://192.168.1.1/hook")

    def test_rejects_localhost_ip(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://127.0.0.1/hook")

    def test_rejects_dns_resolving_to_private(self):
        """A hostname that resolves to a private IP is blocked."""
        with (
            patch(
                "mergeguard.output.notifications.socket.getaddrinfo",
                return_value=[(None, None, None, None, ("10.0.0.5", 443))],
            ),
            pytest.raises(ValueError, match="private address"),
        ):
            _validate_webhook_url("https://evil.example.com/hook")

    def test_allows_dns_resolution_failure(self):
        """DNS resolution failure is allowed (httpx will handle it)."""
        import socket

        with patch(
            "mergeguard.output.notifications.socket.getaddrinfo",
            side_effect=socket.gaierror("Name resolution failed"),
        ):
            # Should not raise
            _validate_webhook_url("https://nonexistent.example.com/hook")


# ── Slack Notifications ──


class TestNotifySlack:
    def test_returns_false_when_no_matching_severity(self):
        report = _make_report(conflicts=[_make_conflict(severity=ConflictSeverity.INFO)])
        result = notify_slack(
            "https://hooks.slack.com/test",
            report,
            "owner/repo",
            notify_on=["critical"],
        )
        assert result is False

    def test_sends_notification_on_matching_severity(self):
        report = _make_report()
        mock_resp = _ok_response()
        with patch("mergeguard.output.notifications._safe_post", return_value=mock_resp):
            result = notify_slack("https://hooks.slack.com/test", report, "owner/repo")
        assert result is True

    def test_payload_contains_pr_number(self):
        report = _make_report()
        mock_resp = _ok_response()
        with patch(
            "mergeguard.output.notifications._safe_post", return_value=mock_resp
        ) as mock_post:
            notify_slack("https://hooks.slack.com/test", report, "owner/repo")
            payload = mock_post.call_args[1]["json"]
            header_text = payload["blocks"][0]["text"]["text"]
            assert "#42" in header_text

    def test_truncates_conflicts_to_5(self):
        conflicts = [_make_conflict(target_pr=i) for i in range(10)]
        report = _make_report(conflicts=conflicts)
        mock_resp = _ok_response()
        with patch(
            "mergeguard.output.notifications._safe_post", return_value=mock_resp
        ) as mock_post:
            notify_slack("https://hooks.slack.com/test", report, "owner/repo")
            payload = mock_post.call_args[1]["json"]
            # Should have a "...and N more" context block
            last_block = payload["blocks"][-1]
            assert last_block["type"] == "context"
            assert "5 more" in last_block["elements"][0]["text"]

    def test_returns_false_on_http_error(self):
        report = _make_report()
        with patch(
            "mergeguard.output.notifications._safe_post",
            side_effect=httpx.ConnectError("fail"),
        ):
            result = notify_slack("https://hooks.slack.com/test", report, "owner/repo")
        assert result is False

    def test_returns_false_when_empty_conflicts(self):
        report = _make_report(conflicts=[])
        result = notify_slack("https://hooks.slack.com/test", report, "owner/repo")
        assert result is False


# ── Teams Notifications ──


class TestNotifyTeams:
    def test_returns_false_when_no_matching_severity(self):
        report = _make_report(conflicts=[_make_conflict(severity=ConflictSeverity.INFO)])
        result = notify_teams(
            "https://teams.webhook.office.com/test",
            report,
            "owner/repo",
            notify_on=["critical"],
        )
        assert result is False

    def test_sends_adaptive_card(self):
        report = _make_report()
        mock_resp = _ok_response()
        with patch(
            "mergeguard.output.notifications._safe_post", return_value=mock_resp
        ) as mock_post:
            result = notify_teams("https://teams.webhook.office.com/test", report, "owner/repo")
            assert result is True
            payload = mock_post.call_args[1]["json"]
            assert payload["type"] == "message"
            card = payload["attachments"][0]["content"]
            assert card["type"] == "AdaptiveCard"

    def test_includes_risk_score_in_facts(self):
        report = _make_report(risk_score=85.0)
        mock_resp = _ok_response()
        with patch(
            "mergeguard.output.notifications._safe_post", return_value=mock_resp
        ) as mock_post:
            notify_teams("https://teams.webhook.office.com/test", report, "owner/repo")
            payload = mock_post.call_args[1]["json"]
            facts = payload["attachments"][0]["content"]["body"][2]["facts"]
            risk_fact = next(f for f in facts if f["title"] == "Risk Score")
            assert "85" in risk_fact["value"]


# ── Per-Team Slack Notifications ──


class TestNotifySlackPerTeam:
    def test_groups_by_owner(self):
        c1 = _make_conflict(owners=["@backend"])
        c2 = _make_conflict(owners=["@frontend"], target_pr=44)
        report = _make_report(conflicts=[c1, c2])

        mock_resp = _ok_response()
        with patch("mergeguard.output.notifications._safe_post", return_value=mock_resp):
            results = notify_slack_per_team(
                report,
                team_channels={
                    "@backend": "https://hooks.slack.com/backend",
                    "@frontend": "https://hooks.slack.com/frontend",
                },
            )
        assert results["@backend"] is True
        assert results["@frontend"] is True

    def test_uses_fallback_for_unowned(self):
        c1 = _make_conflict(owners=[])
        report = _make_report(conflicts=[c1])

        mock_resp = _ok_response()
        with patch("mergeguard.output.notifications._safe_post", return_value=mock_resp):
            results = notify_slack_per_team(
                report,
                team_channels={},
                fallback_webhook="https://hooks.slack.com/default",
            )
        assert results.get("_unowned") is True

    def test_skips_team_without_webhook(self):
        c1 = _make_conflict(owners=["@infra"])
        report = _make_report(conflicts=[c1])

        results = notify_slack_per_team(
            report,
            team_channels={},
            fallback_webhook=None,
        )
        assert results["@infra"] is False

    def test_returns_empty_when_no_matching_severity(self):
        c1 = _make_conflict(severity=ConflictSeverity.INFO, owners=["@backend"])
        report = _make_report(conflicts=[c1])

        results = notify_slack_per_team(
            report,
            team_channels={"@backend": "https://hooks.slack.com/backend"},
            notify_on=["critical"],
        )
        assert results == {}
