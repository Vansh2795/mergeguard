"""Tests for merge queue integration — config, readiness logic."""

from __future__ import annotations

from datetime import UTC, datetime

from mergeguard.core.merge_order import MergeReadiness, compute_merge_readiness
from mergeguard.models import (
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    MergeGuardConfig,
    MergeQueueConfig,
    PRInfo,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_pr(number: int, labels: list[str] | None = None) -> PRInfo:
    now = datetime.now(UTC)
    return PRInfo(
        number=number,
        title=f"PR #{number}",
        author="alice",
        base_branch="main",
        head_branch=f"feature-{number}",
        head_sha=f"sha{number}",
        created_at=now,
        updated_at=now,
        labels=labels or [],
    )


def _make_conflict(
    source_pr: int,
    target_pr: int,
    severity: ConflictSeverity = ConflictSeverity.CRITICAL,
) -> Conflict:
    return Conflict(
        conflict_type=ConflictType.HARD,
        severity=severity,
        source_pr=source_pr,
        target_pr=target_pr,
        file_path="src/main.py",
        description="Test conflict",
        recommendation="Fix it",
    )


def _make_report(
    pr_number: int,
    conflicts: list[Conflict] | None = None,
    labels: list[str] | None = None,
) -> ConflictReport:
    return ConflictReport(
        pr=_make_pr(pr_number, labels=labels),
        conflicts=conflicts or [],
    )


# ── Config tests ─────────────────────────────────────────────────────


class TestMergeQueueConfig:
    def test_defaults(self):
        cfg = MergeQueueConfig()
        assert cfg.enabled is False
        assert cfg.block_on_conflicts is True
        assert cfg.block_severity == "critical"
        assert cfg.status_context == "mergeguard/cross-pr-analysis"
        assert cfg.auto_recheck_on_close is True

    def test_priority_labels_default(self):
        cfg = MergeQueueConfig()
        assert cfg.priority_labels == {
            "merge-priority:high": 100,
            "merge-priority:low": -100,
        }

    def test_custom_block_severity(self):
        cfg = MergeQueueConfig(block_severity="warning")
        assert cfg.block_severity == "warning"

    def test_wired_into_mergeguard_config(self):
        cfg = MergeGuardConfig()
        assert isinstance(cfg.merge_queue, MergeQueueConfig)
        assert cfg.merge_queue.enabled is False

    def test_mergeguard_config_with_merge_queue(self):
        cfg = MergeGuardConfig(merge_queue=MergeQueueConfig(enabled=True))
        assert cfg.merge_queue.enabled is True


# ── Readiness tests ──────────────────────────────────────────────────


class TestMergeReadiness:
    def test_no_conflicts_returns_success(self):
        report = _make_report(42)
        result = compute_merge_readiness(42, [report])
        assert result.is_blocked is False
        assert result.status_state == "success"
        assert result.blocking_prs == []

    def test_critical_conflict_returns_failure(self):
        report = _make_report(
            42,
            conflicts=[_make_conflict(42, 43, ConflictSeverity.CRITICAL)],
        )
        report2 = _make_report(43)
        result = compute_merge_readiness(42, [report, report2])
        assert result.is_blocked is True
        assert result.status_state == "failure"
        assert 43 in result.blocking_prs

    def test_warning_only_with_critical_severity_not_blocked(self):
        report = _make_report(
            42,
            conflicts=[_make_conflict(42, 43, ConflictSeverity.WARNING)],
        )
        result = compute_merge_readiness(42, [report], block_severity="critical")
        assert result.is_blocked is False
        assert result.status_state == "success"

    def test_warning_blocked_when_severity_is_warning(self):
        report = _make_report(
            42,
            conflicts=[_make_conflict(42, 43, ConflictSeverity.WARNING)],
        )
        report2 = _make_report(43)
        result = compute_merge_readiness(42, [report, report2], block_severity="warning")
        assert result.is_blocked is True
        assert result.status_state == "failure"

    def test_priority_label_override(self):
        report = _make_report(
            42,
            conflicts=[_make_conflict(42, 43, ConflictSeverity.CRITICAL)],
            labels=["merge-priority:high"],
        )
        report2 = _make_report(43)
        result = compute_merge_readiness(
            42,
            [report, report2],
            priority_labels={"merge-priority:high": 100},
        )
        assert result.priority_override is True
        assert result.status_state == "success"

    def test_status_description_max_length(self):
        # Create many blocking PRs to test truncation
        conflicts = [_make_conflict(42, i) for i in range(100, 200)]
        report = _make_report(42, conflicts=conflicts)
        other_reports = [_make_report(i) for i in range(100, 200)]
        result = compute_merge_readiness(42, [report] + other_reports)
        assert len(result.status_description) <= 140

    def test_pr_not_in_reports_returns_success(self):
        report = _make_report(99)
        result = compute_merge_readiness(42, [report])
        assert result.is_blocked is False
        assert result.status_state == "success"
        assert "No conflict data" in result.status_description

    def test_info_severity_not_blocked_at_critical(self):
        report = _make_report(
            42,
            conflicts=[_make_conflict(42, 43, ConflictSeverity.INFO)],
        )
        result = compute_merge_readiness(42, [report], block_severity="critical")
        assert result.is_blocked is False

    def test_merge_readiness_dataclass_status_state(self):
        ready = MergeReadiness(pr_number=1, is_blocked=False)
        assert ready.status_state == "success"

        blocked = MergeReadiness(pr_number=1, is_blocked=True)
        assert blocked.status_state == "failure"

        override = MergeReadiness(pr_number=1, is_blocked=True, priority_override=True)
        assert override.status_state == "success"
