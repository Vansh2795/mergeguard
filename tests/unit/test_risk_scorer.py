"""Tests for risk_scorer module."""

from __future__ import annotations

from datetime import datetime

from mergeguard.core.risk_scorer import (
    NO_CONFLICT_DAMPENER,
    _score_conflicts,
    compute_risk_score,
)
from mergeguard.models import (
    AIAttribution,
    Conflict,
    ConflictSeverity,
    ConflictType,
    MergeGuardConfig,
    PRInfo,
)


def make_conflict(severity, target_pr=2):
    return Conflict(
        conflict_type=ConflictType.HARD,
        severity=severity,
        source_pr=1,
        target_pr=target_pr,
        file_path="f.py",
        description="test",
        recommendation="test",
    )


class TestScoreConflicts:
    def test_no_conflicts(self):
        assert _score_conflicts([]) == 0.0

    def test_single_critical(self):
        score = _score_conflicts([make_conflict(ConflictSeverity.CRITICAL)])
        assert score == 100.0

    def test_single_warning(self):
        score = _score_conflicts([make_conflict(ConflictSeverity.WARNING)])
        assert score == 50.0

    def test_single_info(self):
        score = _score_conflicts([make_conflict(ConflictSeverity.INFO)])
        assert score == 15.0

    def test_diminishing_returns(self):
        conflicts = [
            make_conflict(ConflictSeverity.CRITICAL),
            make_conflict(ConflictSeverity.WARNING),
        ]
        score = _score_conflicts(conflicts)
        assert score == 100.0  # 100 + 50*0.5 = 125, capped at 100

    def test_concentrated_criticals_discounted(self):
        """3 CRITICALs from 1 PR -> discount applied (~73.3)."""
        conflicts = [
            make_conflict(ConflictSeverity.CRITICAL, target_pr=5),
            make_conflict(ConflictSeverity.CRITICAL, target_pr=5),
            make_conflict(ConflictSeverity.CRITICAL, target_pr=5),
        ]
        score = _score_conflicts(conflicts)
        # discount = 0.6 + 0.4*(1/3) = 0.7333
        # base = 100 + 100*0.5 + 100*0.25 = 175 -> capped at 100 -> 100 * 0.7333 = 73.33
        assert 73.0 < score < 74.0

    def test_distributed_criticals_no_discount(self):
        """3 CRITICALs from 3 different PRs -> no discount."""
        conflicts = [
            make_conflict(ConflictSeverity.CRITICAL, target_pr=3),
            make_conflict(ConflictSeverity.CRITICAL, target_pr=4),
            make_conflict(ConflictSeverity.CRITICAL, target_pr=5),
        ]
        score = _score_conflicts(conflicts)
        assert score == 100.0


class TestComputeRiskScore:
    def test_zero_risk(self):
        pr = PRInfo(
            number=1,
            title="t",
            author="a",
            base_branch="main",
            head_branch="b",
            head_sha="s",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        score, factors = compute_risk_score(pr, [], 0, 0.0, 0.0, MergeGuardConfig())
        assert score == 0.0

    def test_ai_attribution_penalty(self):
        pr = PRInfo(
            number=1,
            title="t",
            author="a",
            base_branch="main",
            head_branch="b",
            head_sha="s",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            ai_attribution=AIAttribution.AI_CONFIRMED,
        )
        score, factors = compute_risk_score(pr, [], 0, 0.0, 0.0, MergeGuardConfig())
        assert factors["ai_attribution"] == 40.0
        assert score > 0

    def test_blast_radius_boosted_by_conflicting_prs(self):
        """10 conflicts from 10 different PRs → blast_radius = 15 + 40 = 55 (depth=1)."""
        pr = PRInfo(
            number=1,
            title="t",
            author="a",
            base_branch="main",
            head_branch="b",
            head_sha="s",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        conflicts = [
            Conflict(
                conflict_type=ConflictType.BEHAVIORAL,
                severity=ConflictSeverity.WARNING,
                source_pr=1,
                target_pr=i,
                file_path="f.py",
                description="d",
                recommendation="r",
            )
            for i in range(2, 12)  # 10 distinct target PRs
        ]
        _, factors = compute_risk_score(pr, conflicts, 1, 0.0, 0.0, MergeGuardConfig())
        # depth=1 → 15, plus 10 PRs × 4 = 40 → total 55
        assert factors["blast_radius"] == 55.0

    def test_blast_radius_capped_at_100(self):
        """Many conflicts don't exceed 100."""
        pr = PRInfo(
            number=1,
            title="t",
            author="a",
            base_branch="main",
            head_branch="b",
            head_sha="s",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        conflicts = [
            Conflict(
                conflict_type=ConflictType.BEHAVIORAL,
                severity=ConflictSeverity.WARNING,
                source_pr=1,
                target_pr=i,
                file_path="f.py",
                description="d",
                recommendation="r",
            )
            for i in range(2, 52)  # 50 distinct target PRs
        ]
        _, factors = compute_risk_score(pr, conflicts, 5, 0.0, 0.0, MergeGuardConfig())
        assert factors["blast_radius"] == 100.0

    def test_no_conflict_dampening(self):
        """High auxiliary scores are dampened when no conflicts exist."""
        pr = PRInfo(
            number=1,
            title="t",
            author="a",
            base_branch="main",
            head_branch="b",
            head_sha="s",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            ai_attribution=AIAttribution.AI_SUSPECTED,
        )
        # No conflicts, but high churn/pattern/depth to simulate PR #13 scenario
        score, factors = compute_risk_score(
            pr, [], 3, 1.0, 0.5, MergeGuardConfig()
        )
        # Undampened: blast=45*0.25 + pattern=50*0.20 + churn=100*0.15 + ai=20*0.10
        #           = 11.25 + 10.0 + 15.0 + 2.0 = 38.25
        # Dampened:  38.25 * 0.25 = 9.5625
        assert score < 15.0  # Well below the undampened ~38
        # Verify dampener was applied (score ≈ undampened * 0.25)
        undampened = sum(
            factors[k] * w
            for k, w in [
                ("conflict_severity", 0.30),
                ("blast_radius", 0.25),
                ("pattern_deviation", 0.20),
                ("churn_risk", 0.15),
                ("ai_attribution", 0.10),
            ]
        )
        assert abs(score - undampened * NO_CONFLICT_DAMPENER) < 0.001

    def test_dampening_not_applied_with_conflicts(self):
        """Dampener does NOT apply when conflicts exist."""
        pr = PRInfo(
            number=1,
            title="t",
            author="a",
            base_branch="main",
            head_branch="b",
            head_sha="s",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        conflicts = [make_conflict(ConflictSeverity.WARNING)]
        score, factors = compute_risk_score(
            pr, conflicts, 3, 1.0, 0.5, MergeGuardConfig()
        )
        # With conflicts, no dampening — score equals the raw weighted sum
        undampened = sum(
            factors[k] * w
            for k, w in [
                ("conflict_severity", 0.30),
                ("blast_radius", 0.25),
                ("pattern_deviation", 0.20),
                ("churn_risk", 0.15),
                ("ai_attribution", 0.10),
            ]
        )
        assert abs(score - undampened) < 0.001
