"""Composite risk scoring for PRs."""

from __future__ import annotations

from mergeguard.models import (
    AIAttribution,
    Conflict,
    ConflictSeverity,
    MergeGuardConfig,
    PRInfo,
)

# Weight configuration (sums to 1.0)
DEFAULT_WEIGHTS = {
    "conflict_severity": 0.30,
    "blast_radius": 0.25,
    "pattern_deviation": 0.20,
    "churn_risk": 0.15,
    "ai_attribution": 0.10,
}

# ── Scoring constants ──
DEPENDENCY_DEPTH_MULTIPLIER = 15.0  # Points per dependency level
CONFLICTING_PR_MULTIPLIER = 4.0  # Points per conflicting PR
AI_CONFIRMED_PENALTY = 40.0  # Score penalty for confirmed AI PRs
AI_SUSPECTED_PENALTY = 20.0  # Score penalty for suspected AI PRs
CRITICAL_SEVERITY_SCORE = 100.0
WARNING_SEVERITY_SCORE = 50.0
INFO_SEVERITY_SCORE = 15.0
DIMINISHING_RETURN_BASE = 0.5  # Exponent base for diminishing returns
CONCENTRATION_FLOOR = 0.6  # Min discount for concentrated criticals
CONCENTRATION_VARIABLE = 0.4  # Variable portion of concentration discount


def compute_risk_score(
    pr: PRInfo,
    conflicts: list[Conflict],
    dependency_depth: int,  # How deep in dependency graph
    churn_score: float,  # 0-1, from git history
    pattern_deviation_score: float,  # 0-1, from AST comparison
    config: MergeGuardConfig,
) -> tuple[float, dict[str, float]]:
    """Compute a composite risk score (0-100) for a PR.

    Returns (total_score, breakdown_dict) for transparency.
    """
    weights = DEFAULT_WEIGHTS
    factors: dict[str, float] = {}

    # 1. Conflict severity (0-100)
    conflict_score = _score_conflicts(conflicts)
    factors["conflict_severity"] = conflict_score

    # 2. Blast radius (0-100)
    # Based on how many downstream files/modules depend on changed code
    blast_score = min(100.0, dependency_depth * DEPENDENCY_DEPTH_MULTIPLIER)
    # Boost: number of conflicting PRs signals high-traffic code
    num_conflicting = len({c.target_pr for c in conflicts})
    blast_score = min(100.0, blast_score + num_conflicting * CONFLICTING_PR_MULTIPLIER)
    factors["blast_radius"] = blast_score

    # 3. Pattern deviation (0-100)
    # How much does this code deviate from existing patterns in the module
    factors["pattern_deviation"] = pattern_deviation_score * 100.0

    # 4. Churn risk (0-100)
    # Are the changed files historically buggy? (high revert/hotfix rate)
    factors["churn_risk"] = churn_score * 100.0

    # 5. AI attribution (0-100)
    # AI-generated PRs get a modest penalty because data shows higher bug rates
    ai_score = 0.0
    if pr.ai_attribution == AIAttribution.AI_CONFIRMED:
        ai_score = AI_CONFIRMED_PENALTY
    elif pr.ai_attribution == AIAttribution.AI_SUSPECTED:
        ai_score = AI_SUSPECTED_PENALTY
    factors["ai_attribution"] = ai_score

    # Weighted sum
    total = sum(factors[k] * weights[k] for k in weights)
    total = min(100.0, max(0.0, total))

    return total, factors


def _score_conflicts(conflicts: list[Conflict]) -> float:
    """Score conflicts by severity. Critical = 100, Warning = 50, Info = 15."""
    if not conflicts:
        return 0.0
    severity_scores = {
        ConflictSeverity.CRITICAL: CRITICAL_SEVERITY_SCORE,
        ConflictSeverity.WARNING: WARNING_SEVERITY_SCORE,
        ConflictSeverity.INFO: INFO_SEVERITY_SCORE,
    }
    # Take the max severity, plus a diminishing contribution from others
    scores = sorted(
        [severity_scores[c.severity] for c in conflicts],
        reverse=True,
    )
    total = scores[0]
    for i, s in enumerate(scores[1:], start=1):
        total += s * (DIMINISHING_RETURN_BASE**i)
    base_score = min(100.0, total)

    # Concentration discount: multiple CRITICALs from fewer PRs → lower effective risk
    critical_conflicts = [c for c in conflicts if c.severity == ConflictSeverity.CRITICAL]
    if critical_conflicts:
        unique_prs = len({c.target_pr for c in critical_conflicts})
        n = len(critical_conflicts)
        if n > unique_prs:
            discount = CONCENTRATION_FLOOR + CONCENTRATION_VARIABLE * (unique_prs / n)
            base_score *= discount

    return min(100.0, base_score)
