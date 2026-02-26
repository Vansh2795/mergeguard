"""Tests for risk_scorer module."""
from __future__ import annotations
import pytest
from mergeguard.core.risk_scorer import compute_risk_score, _score_conflicts
from mergeguard.models import (
    PRInfo, Conflict, ConflictSeverity, ConflictType,
    AIAttribution, MergeGuardConfig,
)
from datetime import datetime


def make_conflict(severity):
    return Conflict(
        conflict_type=ConflictType.HARD, severity=severity,
        source_pr=1, target_pr=2, file_path="f.py",
        description="test", recommendation="test",
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


class TestComputeRiskScore:
    def test_zero_risk(self):
        pr = PRInfo(
            number=1, title="t", author="a", base_branch="main",
            head_branch="b", head_sha="s",
            created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
        )
        score, factors = compute_risk_score(
            pr, [], 0, 0.0, 0.0, MergeGuardConfig()
        )
        assert score == 0.0

    def test_ai_attribution_penalty(self):
        pr = PRInfo(
            number=1, title="t", author="a", base_branch="main",
            head_branch="b", head_sha="s",
            created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
            ai_attribution=AIAttribution.AI_CONFIRMED,
        )
        score, factors = compute_risk_score(
            pr, [], 0, 0.0, 0.0, MergeGuardConfig()
        )
        assert factors["ai_attribution"] == 40.0
        assert score > 0
