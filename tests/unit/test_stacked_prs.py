"""Tests for stacked PR detection, demotion, and integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mergeguard.analysis.stacked_prs import (
    build_stack_lookup,
    detect_stacks,
)
from mergeguard.core.engine import _demote_intra_stack_conflicts
from mergeguard.core.merge_order import compute_merge_readiness
from mergeguard.models import (
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    MergeGuardConfig,
    PRInfo,
    StackedPRConfig,
    StackGroup,
)

# ── Helpers ──────────────────────────────────────────────────────────

_T0 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


def _make_pr(
    number: int,
    *,
    base_branch: str = "main",
    head_branch: str | None = None,
    labels: list[str] | None = None,
    description: str = "",
    created_at: datetime | None = None,
) -> PRInfo:
    return PRInfo(
        number=number,
        title=f"PR #{number}",
        author="alice",
        base_branch=base_branch,
        head_branch=head_branch or f"feature-{number}",
        head_sha=f"sha{number}",
        created_at=created_at or _T0 + timedelta(hours=number),
        updated_at=created_at or _T0 + timedelta(hours=number),
        labels=labels or [],
        description=description,
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
    now = datetime.now(UTC)
    return ConflictReport(
        pr=PRInfo(
            number=pr_number,
            title=f"PR #{pr_number}",
            author="alice",
            base_branch="main",
            head_branch=f"feature-{pr_number}",
            head_sha=f"sha{pr_number}",
            created_at=now,
            updated_at=now,
            labels=labels or [],
        ),
        conflicts=conflicts or [],
    )


# ── Config tests ─────────────────────────────────────────────────────


class TestStackedPRConfig:
    def test_defaults(self):
        cfg = StackedPRConfig()
        assert cfg.enabled is True
        assert cfg.detection == ["branch_chain", "labels"]
        assert cfg.demote_severity is True
        assert cfg.label_pattern == "stack:"

    def test_custom_detection_list(self):
        cfg = StackedPRConfig(detection=["graphite"])
        assert cfg.detection == ["graphite"]

    def test_wired_into_mergeguard_config(self):
        cfg = MergeGuardConfig()
        assert isinstance(cfg.stacked_prs, StackedPRConfig)
        assert cfg.stacked_prs.enabled is True

    def test_mergeguard_config_with_stacked_prs(self):
        cfg = MergeGuardConfig(stacked_prs=StackedPRConfig(enabled=False))
        assert cfg.stacked_prs.enabled is False


# ── Branch chain detection ───────────────────────────────────────────


class TestBranchChainDetection:
    def test_two_pr_stack(self):
        """A→B: PR A targets main, PR B targets A's head branch."""
        pr_a = _make_pr(10, base_branch="main", head_branch="feature/auth")
        pr_b = _make_pr(11, base_branch="feature/auth", head_branch="feature/auth-v2")
        config = StackedPRConfig(detection=["branch_chain"])

        groups = detect_stacks([pr_a, pr_b], config)

        assert len(groups) == 1
        assert groups[0].pr_numbers == [10, 11]
        assert groups[0].detection_method == "branch_chain"
        assert groups[0].base_branch == "main"
        assert groups[0].is_complete is True

    def test_three_pr_stack(self):
        """A→B→C chain."""
        pr_a = _make_pr(10, base_branch="main", head_branch="feature/step-1")
        pr_b = _make_pr(11, base_branch="feature/step-1", head_branch="feature/step-2")
        pr_c = _make_pr(12, base_branch="feature/step-2", head_branch="feature/step-3")
        config = StackedPRConfig(detection=["branch_chain"])

        groups = detect_stacks([pr_a, pr_b, pr_c], config)

        assert len(groups) == 1
        assert groups[0].pr_numbers == [10, 11, 12]

    def test_independent_prs_no_stacks(self):
        """PRs all target main with no linking — no stacks detected."""
        prs = [
            _make_pr(10, base_branch="main", head_branch="feat-a"),
            _make_pr(11, base_branch="main", head_branch="feat-b"),
            _make_pr(12, base_branch="main", head_branch="feat-c"),
        ]
        config = StackedPRConfig(detection=["branch_chain"])

        groups = detect_stacks(prs, config)
        assert groups == []

    def test_circular_reference_handled(self):
        """Circular refs should not cause infinite loop."""
        # Simulate circular: A→B→A (shouldn't happen in practice but guard it)
        pr_a = _make_pr(10, base_branch="main", head_branch="branch-a")
        pr_b = _make_pr(11, base_branch="branch-a", head_branch="branch-b")
        # A third PR that creates a "pseudo-circle" by pointing back
        pr_c = _make_pr(12, base_branch="branch-b", head_branch="branch-a")
        config = StackedPRConfig(detection=["branch_chain"])

        # Should not hang
        groups = detect_stacks([pr_a, pr_b, pr_c], config)
        # Should detect A→B→C as a chain (C's head happens to match A's head, but no infinite loop)
        assert len(groups) >= 1
        for g in groups:
            # No duplicate PR numbers within a group
            assert len(g.pr_numbers) == len(set(g.pr_numbers))

    def test_fork_off_stack_picks_oldest(self):
        """When two PRs target the same base, pick the oldest by created_at."""
        pr_a = _make_pr(10, base_branch="main", head_branch="base-branch")
        pr_b = _make_pr(
            11,
            base_branch="base-branch",
            head_branch="fork-1",
            created_at=_T0 + timedelta(hours=1),
        )
        pr_c = _make_pr(
            12,
            base_branch="base-branch",
            head_branch="fork-2",
            created_at=_T0 + timedelta(hours=2),
        )
        config = StackedPRConfig(detection=["branch_chain"])

        groups = detect_stacks([pr_a, pr_b, pr_c], config)

        assert len(groups) == 1
        # Should pick pr_b (oldest created_at among forks)
        assert groups[0].pr_numbers == [10, 11]

    def test_multiple_independent_stacks(self):
        """Two separate stacks detected independently."""
        # Stack 1: A→B
        pr_a = _make_pr(10, base_branch="main", head_branch="stack1-base")
        pr_b = _make_pr(11, base_branch="stack1-base", head_branch="stack1-tip")
        # Stack 2: C→D
        pr_c = _make_pr(20, base_branch="main", head_branch="stack2-base")
        pr_d = _make_pr(21, base_branch="stack2-base", head_branch="stack2-tip")
        config = StackedPRConfig(detection=["branch_chain"])

        groups = detect_stacks([pr_a, pr_b, pr_c, pr_d], config)

        assert len(groups) == 2
        all_prs = {n for g in groups for n in g.pr_numbers}
        assert all_prs == {10, 11, 20, 21}

    def test_disabled_returns_empty(self):
        pr_a = _make_pr(10, base_branch="main", head_branch="feature/auth")
        pr_b = _make_pr(11, base_branch="feature/auth", head_branch="feature/auth-v2")
        config = StackedPRConfig(enabled=False)

        groups = detect_stacks([pr_a, pr_b], config)
        assert groups == []


# ── Label detection ──────────────────────────────────────────────────


class TestLabelDetection:
    def test_group_by_matching_labels(self):
        pr_a = _make_pr(10, labels=["stack:auth"])
        pr_b = _make_pr(11, labels=["stack:auth"])
        pr_c = _make_pr(12, labels=["stack:billing"])
        config = StackedPRConfig(detection=["labels"])

        groups = detect_stacks([pr_a, pr_b, pr_c], config)

        # Only "auth" group has 2+ PRs
        assert len(groups) == 1
        assert groups[0].group_id == "label-auth"
        assert set(groups[0].pr_numbers) == {10, 11}
        assert groups[0].detection_method == "labels"

    def test_custom_label_pattern(self):
        pr_a = _make_pr(10, labels=["stacked/auth"])
        pr_b = _make_pr(11, labels=["stacked/auth"])
        config = StackedPRConfig(detection=["labels"], label_pattern="stacked/")

        groups = detect_stacks([pr_a, pr_b], config)

        assert len(groups) == 1
        assert groups[0].group_id == "label-auth"

    def test_order_by_created_at(self):
        pr_a = _make_pr(11, labels=["stack:auth"], created_at=_T0 + timedelta(hours=2))
        pr_b = _make_pr(10, labels=["stack:auth"], created_at=_T0 + timedelta(hours=1))
        config = StackedPRConfig(detection=["labels"])

        groups = detect_stacks([pr_a, pr_b], config)

        assert groups[0].pr_numbers == [10, 11]  # Older first

    def test_single_pr_no_group(self):
        pr_a = _make_pr(10, labels=["stack:auth"])
        config = StackedPRConfig(detection=["labels"])

        groups = detect_stacks([pr_a], config)
        assert groups == []

    def test_multiple_label_groups(self):
        prs = [
            _make_pr(10, labels=["stack:auth"]),
            _make_pr(11, labels=["stack:auth"]),
            _make_pr(20, labels=["stack:billing"]),
            _make_pr(21, labels=["stack:billing"]),
        ]
        config = StackedPRConfig(detection=["labels"])

        groups = detect_stacks(prs, config)
        assert len(groups) == 2


# ── Graphite detection ───────────────────────────────────────────────


class TestGraphiteDetection:
    def test_parse_graphite_base_trailer(self):
        pr_a = _make_pr(10, base_branch="main", head_branch="auth-base")
        pr_b = _make_pr(
            11,
            base_branch="auth-base",
            head_branch="auth-v2",
            description="Some description\n\nGraphite-base: main",
        )
        pr_c = _make_pr(
            12,
            base_branch="auth-v2",
            head_branch="auth-v3",
            description="Graphite-base: auth-base",
        )
        config = StackedPRConfig(detection=["graphite"])

        groups = detect_stacks([pr_a, pr_b, pr_c], config)

        # pr_b (Graphite-base: main) is a root, pr_c (Graphite-base:
        # auth-base) chains off pr_a's head. But pr_a has no Graphite
        # metadata, so the chain may not fully connect. Verify no crash.
        assert isinstance(groups, list)

    def test_graphite_chain(self):
        """Proper Graphite chain: root parented on main, child parented on root's head."""
        pr_a = _make_pr(
            10,
            base_branch="main",
            head_branch="feat-step1",
            description="Graphite-base: main",
        )
        pr_b = _make_pr(
            11,
            base_branch="feat-step1",
            head_branch="feat-step2",
            description="Graphite-base: feat-step1",
        )
        config = StackedPRConfig(detection=["graphite"])

        groups = detect_stacks([pr_a, pr_b], config)

        assert len(groups) == 1
        assert groups[0].pr_numbers == [10, 11]
        assert groups[0].detection_method == "graphite"

    def test_no_graphite_metadata_no_groups(self):
        prs = [_make_pr(10), _make_pr(11)]
        config = StackedPRConfig(detection=["graphite"])

        groups = detect_stacks(prs, config)
        assert groups == []


# ── Deduplication ────────────────────────────────────────────────────


class TestDeduplication:
    def test_branch_chain_takes_priority_over_labels(self):
        """Same PRs detected by both branch_chain and labels — branch_chain wins."""
        pr_a = _make_pr(
            10,
            base_branch="main",
            head_branch="auth-base",
            labels=["stack:auth"],
        )
        pr_b = _make_pr(
            11,
            base_branch="auth-base",
            head_branch="auth-v2",
            labels=["stack:auth"],
        )
        config = StackedPRConfig(detection=["branch_chain", "labels"])

        groups = detect_stacks([pr_a, pr_b], config)

        # Should get only 1 group (branch_chain wins)
        assert len(groups) == 1
        assert groups[0].detection_method == "branch_chain"


# ── Demotion ─────────────────────────────────────────────────────────


class TestDemoteIntraStackConflicts:
    def test_critical_demoted_to_info(self):
        group = StackGroup(
            group_id="chain-auth",
            pr_numbers=[10, 11],
            base_branch="main",
            detection_method="branch_chain",
        )
        lookup = build_stack_lookup([group])

        conflict = _make_conflict(10, 11, ConflictSeverity.CRITICAL)
        _demote_intra_stack_conflicts([conflict], lookup)

        assert conflict.is_intra_stack is True
        assert conflict.severity == ConflictSeverity.INFO
        assert conflict.original_severity == ConflictSeverity.CRITICAL

    def test_warning_demoted_to_info(self):
        group = StackGroup(
            group_id="chain-auth",
            pr_numbers=[10, 11],
            base_branch="main",
            detection_method="branch_chain",
        )
        lookup = build_stack_lookup([group])

        conflict = _make_conflict(10, 11, ConflictSeverity.WARNING)
        _demote_intra_stack_conflicts([conflict], lookup)

        assert conflict.is_intra_stack is True
        assert conflict.severity == ConflictSeverity.INFO
        assert conflict.original_severity == ConflictSeverity.WARNING

    def test_info_stays_info(self):
        group = StackGroup(
            group_id="chain-auth",
            pr_numbers=[10, 11],
            base_branch="main",
            detection_method="branch_chain",
        )
        lookup = build_stack_lookup([group])

        conflict = _make_conflict(10, 11, ConflictSeverity.INFO)
        _demote_intra_stack_conflicts([conflict], lookup)

        assert conflict.is_intra_stack is True
        assert conflict.severity == ConflictSeverity.INFO
        assert conflict.original_severity == ConflictSeverity.INFO

    def test_cross_stack_conflicts_unchanged(self):
        group = StackGroup(
            group_id="chain-auth",
            pr_numbers=[10, 11],
            base_branch="main",
            detection_method="branch_chain",
        )
        lookup = build_stack_lookup([group])

        # PR 10 vs PR 20 — different stacks
        conflict = _make_conflict(10, 20, ConflictSeverity.CRITICAL)
        _demote_intra_stack_conflicts([conflict], lookup)

        assert conflict.is_intra_stack is False
        assert conflict.severity == ConflictSeverity.CRITICAL
        assert conflict.original_severity is None

    def test_unstacked_pr_conflicts_unchanged(self):
        lookup: dict[int, StackGroup] = {}  # No stacks

        conflict = _make_conflict(10, 11, ConflictSeverity.CRITICAL)
        _demote_intra_stack_conflicts([conflict], lookup)

        assert conflict.is_intra_stack is False
        assert conflict.severity == ConflictSeverity.CRITICAL
        assert conflict.original_severity is None

    def test_mixed_conflicts(self):
        """Some intra-stack, some cross-stack — only intra-stack demoted."""
        group = StackGroup(
            group_id="chain-auth",
            pr_numbers=[10, 11, 12],
            base_branch="main",
            detection_method="branch_chain",
        )
        lookup = build_stack_lookup([group])

        conflicts = [
            _make_conflict(10, 11, ConflictSeverity.CRITICAL),  # intra-stack
            _make_conflict(10, 20, ConflictSeverity.CRITICAL),  # cross-stack
            _make_conflict(11, 12, ConflictSeverity.WARNING),  # intra-stack
        ]
        _demote_intra_stack_conflicts(conflicts, lookup)

        assert conflicts[0].is_intra_stack is True
        assert conflicts[0].severity == ConflictSeverity.INFO
        assert conflicts[1].is_intra_stack is False
        assert conflicts[1].severity == ConflictSeverity.CRITICAL
        assert conflicts[2].is_intra_stack is True
        assert conflicts[2].severity == ConflictSeverity.INFO


# ── build_stack_lookup ───────────────────────────────────────────────


class TestBuildStackLookup:
    def test_lookup_maps_all_prs(self):
        group = StackGroup(
            group_id="chain-auth",
            pr_numbers=[10, 11, 12],
            base_branch="main",
            detection_method="branch_chain",
        )
        lookup = build_stack_lookup([group])

        assert 10 in lookup
        assert 11 in lookup
        assert 12 in lookup
        assert lookup[10].group_id == "chain-auth"

    def test_empty_groups_empty_lookup(self):
        assert build_stack_lookup([]) == {}

    def test_multiple_groups(self):
        g1 = StackGroup(
            group_id="chain-a",
            pr_numbers=[10, 11],
            base_branch="main",
            detection_method="branch_chain",
        )
        g2 = StackGroup(
            group_id="chain-b",
            pr_numbers=[20, 21],
            base_branch="main",
            detection_method="branch_chain",
        )
        lookup = build_stack_lookup([g1, g2])

        assert lookup[10].group_id == "chain-a"
        assert lookup[20].group_id == "chain-b"


# ── Integration: merge readiness ─────────────────────────────────────


class TestIntraStackMergeReadiness:
    def test_intra_stack_conflicts_dont_block(self):
        """Intra-stack conflicts should not block merge readiness."""
        conflict = _make_conflict(42, 43, ConflictSeverity.CRITICAL)
        conflict.is_intra_stack = True
        conflict.original_severity = ConflictSeverity.CRITICAL
        conflict.severity = ConflictSeverity.INFO  # Demoted

        report = _make_report(42, conflicts=[conflict])
        report2 = _make_report(43)

        result = compute_merge_readiness(42, [report, report2])
        assert result.is_blocked is False

    def test_mix_of_intra_and_cross_stack_blocks(self):
        """Cross-stack CRITICAL blocks, intra-stack does not."""
        intra = _make_conflict(42, 43, ConflictSeverity.INFO)
        intra.is_intra_stack = True
        intra.original_severity = ConflictSeverity.CRITICAL

        cross = _make_conflict(42, 44, ConflictSeverity.CRITICAL)

        report = _make_report(42, conflicts=[intra, cross])
        report2 = _make_report(43)
        report3 = _make_report(44)

        result = compute_merge_readiness(42, [report, report2, report3])
        assert result.is_blocked is True
        assert 44 in result.blocking_prs
        assert 43 not in result.blocking_prs


# ── StackGroup model ─────────────────────────────────────────────────


class TestStackGroupModel:
    def test_defaults(self):
        g = StackGroup(
            group_id="test",
            pr_numbers=[1, 2],
            base_branch="main",
            detection_method="branch_chain",
        )
        assert g.is_complete is True

    def test_incomplete(self):
        g = StackGroup(
            group_id="test",
            pr_numbers=[1, 3],
            base_branch="main",
            detection_method="branch_chain",
            is_complete=False,
        )
        assert g.is_complete is False
