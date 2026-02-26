"""Regression detection against decisions log.

Detects when a PR re-introduces code or patterns that were
deliberately removed or migrated in recently merged PRs.
"""

from __future__ import annotations

from mergeguard.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    Decision,
    PRInfo,
)
from mergeguard.storage.decisions_log import DecisionsLog


def detect_regressions(
    pr: PRInfo,
    decisions_log: DecisionsLog,
) -> list[Conflict]:
    """Check if the PR re-introduces something recently removed/changed.

    Compares the PR's changed symbols and files against the decisions
    log to detect regressions.

    Args:
        pr: The PR being analyzed.
        decisions_log: The decisions log to check against.

    Returns:
        List of regression conflicts found.
    """
    pr_symbols = list(pr.symbol_names)
    pr_files = [f.path for f in pr.changed_files]

    regressions = decisions_log.find_regressions(pr_symbols, pr_files)

    return [_decision_to_conflict(pr.number, decision) for decision in regressions]


def _decision_to_conflict(pr_number: int, decision: Decision) -> Conflict:
    """Convert a regression decision match into a Conflict object."""
    return Conflict(
        conflict_type=ConflictType.REGRESSION,
        severity=ConflictSeverity.WARNING,
        source_pr=pr_number,
        target_pr=decision.pr_number,
        file_path=decision.file_path or "<unknown>",
        symbol_name=decision.entity,
        description=(
            f"This PR re-introduces `{decision.entity}` which was "
            f"deliberately {decision.decision_type.value}d in "
            f"PR #{decision.pr_number} "
            f"({decision.description})."
        ),
        recommendation=(
            f"Check if re-introducing `{decision.entity}` is intentional. "
            f"The original change was made by @{decision.author} in "
            f"PR #{decision.pr_number}."
        ),
    )
