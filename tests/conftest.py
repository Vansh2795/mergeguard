"""Shared test fixtures for MergeGuard."""

from __future__ import annotations

import pytest
from datetime import datetime

from mergeguard.models import (
    PRInfo, ChangedFile, ChangedSymbol, Symbol, Conflict, ConflictReport,
    ConflictSeverity, ConflictType, SymbolType, FileChangeStatus,
    AIAttribution, MergeGuardConfig, Decision, DecisionType, DecisionsEntry,
)


@pytest.fixture
def sample_pr() -> PRInfo:
    return PRInfo(
        number=42,
        title="Add user authentication",
        author="alice",
        base_branch="main",
        head_branch="feature/auth",
        head_sha="abc123def456",
        created_at=datetime(2026, 1, 15, 10, 0, 0),
        updated_at=datetime(2026, 1, 16, 14, 30, 0),
        labels=["feature"],
        description="Implements JWT-based authentication",
    )


@pytest.fixture
def other_pr() -> PRInfo:
    return PRInfo(
        number=43,
        title="Refactor user module",
        author="bob",
        base_branch="main",
        head_branch="refactor/user",
        head_sha="def789ghi012",
        created_at=datetime(2026, 1, 14, 9, 0, 0),
        updated_at=datetime(2026, 1, 16, 11, 0, 0),
        labels=["refactor"],
        description="Cleans up user module structure",
    )


@pytest.fixture
def sample_symbol() -> Symbol:
    return Symbol(
        name="get_user_by_id",
        symbol_type=SymbolType.FUNCTION,
        file_path="src/users/service.py",
        start_line=45,
        end_line=67,
        signature="def get_user_by_id(user_id: int) -> User",
    )


@pytest.fixture
def sample_changed_file() -> ChangedFile:
    return ChangedFile(
        path="src/users/service.py",
        status=FileChangeStatus.MODIFIED,
        additions=15,
        deletions=5,
        patch="@@ -45,10 +45,20 @@\n-    old line\n+    new line",
    )


@pytest.fixture
def sample_conflict() -> Conflict:
    return Conflict(
        conflict_type=ConflictType.HARD,
        severity=ConflictSeverity.CRITICAL,
        source_pr=42,
        target_pr=43,
        file_path="src/users/service.py",
        symbol_name="get_user_by_id",
        description="Both PRs modify get_user_by_id at overlapping lines.",
        recommendation="Coordinate with the other PR author.",
    )


@pytest.fixture
def sample_report(sample_pr, sample_conflict) -> ConflictReport:
    return ConflictReport(
        pr=sample_pr,
        conflicts=[sample_conflict],
        risk_score=75.0,
        risk_factors={"conflict_severity": 100.0, "blast_radius": 30.0},
        no_conflict_prs=[44, 45],
        analysis_duration_ms=1250,
    )


@pytest.fixture
def empty_report(sample_pr) -> ConflictReport:
    return ConflictReport(
        pr=sample_pr,
        conflicts=[],
        risk_score=0.0,
        no_conflict_prs=[43, 44, 45],
        analysis_duration_ms=800,
    )


@pytest.fixture
def default_config() -> MergeGuardConfig:
    return MergeGuardConfig()


@pytest.fixture
def sample_decision() -> Decision:
    return Decision(
        decision_type=DecisionType.REMOVAL,
        entity="legacy_auth_handler",
        file_path="src/auth/legacy.py",
        description="Removed legacy authentication handler in favor of JWT",
        pr_number=40,
        merged_at=datetime(2026, 1, 10, 12, 0, 0),
        author="carol",
    )
