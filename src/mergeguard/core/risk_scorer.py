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
    blast_score = min(100.0, dependency_depth * 15.0)  # Each dependency level = 15 points
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
        ai_score = 40.0  # Confirmed AI: moderate penalty
    elif pr.ai_attribution == AIAttribution.AI_SUSPECTED:
        ai_score = 20.0  # Suspected AI: mild penalty
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
        ConflictSeverity.CRITICAL: 100.0,
        ConflictSeverity.WARNING: 50.0,
        ConflictSeverity.INFO: 15.0,
    }
    # Take the max severity, plus a diminishing contribution from others
    scores = sorted(
        [severity_scores[c.severity] for c in conflicts],
        reverse=True,
    )
    total = scores[0]
    for i, s in enumerate(scores[1:], start=1):
        total += s * (0.5**i)  # Diminishing returns
    return min(100.0, total)
