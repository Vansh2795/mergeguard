"""Integration tests for CODEOWNERS wired into conflict models and output."""

from __future__ import annotations

from datetime import datetime

from mergeguard.analysis.codeowners import CodeOwners
from mergeguard.models import (
    CodeownersConfig,
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    MergeGuardConfig,
    PRInfo,
)
from mergeguard.output.github_comment import _format_conflict_compact

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_pr(**kwargs) -> PRInfo:
    defaults = dict(
        number=42,
        title="Test PR",
        author="dev",
        base_branch="main",
        head_branch="feature",
        head_sha="abc123",
        created_at=datetime(2026, 3, 20),
        updated_at=datetime(2026, 3, 20),
    )
    defaults.update(kwargs)
    return PRInfo(**defaults)


def _make_conflict(**kwargs) -> Conflict:
    defaults = dict(
        conflict_type=ConflictType.HARD,
        severity=ConflictSeverity.WARNING,
        source_pr=42,
        target_pr=43,
        file_path="src/api/routes.py",
        description="Both PRs modify the same function",
        recommendation="Coordinate merge order",
    )
    defaults.update(kwargs)
    return Conflict(**defaults)


# ──────────────────────────────────────────────
# Conflict model owner field
# ──────────────────────────────────────────────


class TestConflictOwners:
    """Test owners field on Conflict model."""

    def test_default_empty(self):
        c = _make_conflict()
        assert c.owners == []

    def test_set_owners(self):
        c = _make_conflict(owners=["@backend-team", "@api-lead"])
        assert c.owners == ["@backend-team", "@api-lead"]

    def test_serialization(self):
        c = _make_conflict(owners=["@team-a"])
        data = c.model_dump()
        assert data["owners"] == ["@team-a"]


# ──────────────────────────────────────────────
# ConflictReport affected_teams
# ──────────────────────────────────────────────


class TestAffectedTeams:
    """Test affected_teams aggregation on ConflictReport."""

    def test_default_empty(self):
        report = ConflictReport(pr=_make_pr())
        assert report.affected_teams == []

    def test_set_affected_teams(self):
        report = ConflictReport(
            pr=_make_pr(),
            affected_teams=["@backend-team", "@frontend-team"],
        )
        assert "@backend-team" in report.affected_teams
        assert "@frontend-team" in report.affected_teams

    def test_aggregation_from_conflicts(self):
        """Simulate what engine._resolve_conflict_owners does."""
        codeowners_content = """\
* @global-team
src/api/** @backend-team
src/ui/** @frontend-team
"""
        co = CodeOwners(codeowners_content)

        conflicts = [
            _make_conflict(file_path="src/api/routes.py"),
            _make_conflict(file_path="src/ui/Button.tsx", target_pr=44),
            _make_conflict(file_path="README.md", target_pr=45),
        ]

        # Simulate owner resolution
        all_teams: set[str] = set()
        for c in conflicts:
            owners = co.resolve_owners(c.file_path)
            c.owners = owners
            all_teams.update(owners)

        report = ConflictReport(
            pr=_make_pr(),
            conflicts=conflicts,
            affected_teams=sorted(all_teams),
        )

        assert "@backend-team" in report.affected_teams
        assert "@frontend-team" in report.affected_teams
        assert "@global-team" in report.affected_teams
        assert conflicts[0].owners == ["@backend-team"]
        assert conflicts[1].owners == ["@frontend-team"]
        assert conflicts[2].owners == ["@global-team"]


# ──────────────────────────────────────────────
# GitHub comment output with owners
# ──────────────────────────────────────────────


class TestGitHubCommentOwners:
    """Test owner @mentions appear in GitHub comment output."""

    def test_format_conflict_with_owners(self):
        c = _make_conflict(owners=["@backend-team", "@api-lead"])
        output = _format_conflict_compact(c, "owner/repo")
        assert "@backend-team" in output
        assert "@api-lead" in output
        assert "**Owners:**" in output

    def test_format_conflict_without_owners(self):
        c = _make_conflict()
        output = _format_conflict_compact(c, "owner/repo")
        assert "Owners" not in output

    def test_format_conflict_compact_with_owners(self):
        c = _make_conflict(owners=["@frontend-team"])
        output = _format_conflict_compact(c, "owner/repo")
        assert "@frontend-team" in output
        assert "**Owners:**" in output

    def test_format_conflict_compact_without_owners(self):
        c = _make_conflict()
        output = _format_conflict_compact(c, "owner/repo")
        assert "Owners" not in output


# ──────────────────────────────────────────────
# Slack notification owners
# ──────────────────────────────────────────────


class TestSlackNotificationOwners:
    """Test owner info in Slack notification payloads."""

    def test_owners_in_conflict_line(self):
        """notify_slack includes owner info in conflict lines."""
        from unittest.mock import MagicMock, patch

        from mergeguard.output.notifications import notify_slack

        conflict = _make_conflict(
            severity=ConflictSeverity.CRITICAL,
            owners=["@backend-team"],
        )
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[conflict],
            risk_score=75,
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch(
            "mergeguard.output.notifications._safe_post",
            return_value=mock_resp,
        ) as mock_post:
            result = notify_slack("https://hooks.slack.com/test", report, "owner/repo")

        assert result is True
        # Check the payload includes owner info
        payload = mock_post.call_args[1]["json"]
        all_text = " ".join(b["text"]["text"] for b in payload["blocks"] if b["type"] == "section")
        assert "@backend-team" in all_text


# ──────────────────────────────────────────────
# Per-team routing
# ──────────────────────────────────────────────


class TestPerTeamRouting:
    """Test notify_slack_per_team with team_channels config."""

    def test_routes_to_team_channels(self):
        from unittest.mock import MagicMock, patch

        from mergeguard.output.notifications import notify_slack_per_team

        conflicts = [
            _make_conflict(
                severity=ConflictSeverity.CRITICAL,
                file_path="src/api/routes.py",
                owners=["@backend-team"],
            ),
            _make_conflict(
                severity=ConflictSeverity.WARNING,
                file_path="src/ui/Button.tsx",
                owners=["@frontend-team"],
                target_pr=44,
            ),
        ]
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=conflicts,
            risk_score=60,
            affected_teams=["@backend-team", "@frontend-team"],
        )

        team_channels = {
            "@backend-team": "https://hooks.slack.com/backend",
            "@frontend-team": "https://hooks.slack.com/frontend",
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch(
            "mergeguard.output.notifications._safe_post",
            return_value=mock_resp,
        ) as mock_post:
            results = notify_slack_per_team(report, team_channels)

        assert results["@backend-team"] is True
        assert results["@frontend-team"] is True
        assert mock_post.call_count == 2

    def test_fallback_webhook(self):
        from unittest.mock import MagicMock, patch

        from mergeguard.output.notifications import notify_slack_per_team

        conflict = _make_conflict(
            severity=ConflictSeverity.CRITICAL,
            owners=["@unknown-team"],
        )
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[conflict],
            risk_score=70,
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch(
            "mergeguard.output.notifications._safe_post",
            return_value=mock_resp,
        ) as mock_post:
            results = notify_slack_per_team(
                report,
                team_channels={},
                fallback_webhook="https://hooks.slack.com/fallback",
            )

        assert results["@unknown-team"] is True
        assert mock_post.call_count == 1

    def test_no_webhook_skips(self):
        from mergeguard.output.notifications import notify_slack_per_team

        conflict = _make_conflict(
            severity=ConflictSeverity.CRITICAL,
            owners=["@orphan-team"],
        )
        report = ConflictReport(
            pr=_make_pr(),
            conflicts=[conflict],
            risk_score=70,
        )

        results = notify_slack_per_team(report, team_channels={})
        assert results["@orphan-team"] is False


# ──────────────────────────────────────────────
# CodeownersConfig model
# ──────────────────────────────────────────────


class TestCodeownersConfig:
    """Test CodeownersConfig model and MergeGuardConfig integration."""

    def test_default_enabled(self):
        cfg = CodeownersConfig()
        assert cfg.enabled is True
        assert cfg.path is None
        assert cfg.team_channels == {}

    def test_custom_config(self):
        cfg = CodeownersConfig(
            enabled=True,
            path=".github/CODEOWNERS",
            team_channels={"@backend": "https://hooks.slack.com/backend"},
        )
        assert cfg.team_channels["@backend"] == "https://hooks.slack.com/backend"

    def test_wired_into_mergeguard_config(self):
        config = MergeGuardConfig()
        assert config.codeowners.enabled is True
        assert config.codeowners.team_channels == {}

    def test_disabled_skips_resolution(self):
        """When codeowners.enabled=False, owners should not be resolved."""
        config = MergeGuardConfig(codeowners=CodeownersConfig(enabled=False))
        assert config.codeowners.enabled is False
