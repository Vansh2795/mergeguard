"""Template-based fix suggestions — zero-cost, no API key needed.

Generates contextual fix suggestions from conflict metadata (type, symbol,
file path, PR numbers) without any LLM calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mergeguard.models import Conflict

from mergeguard.models import ConflictType


def _hard_suggestion(conflict: Conflict) -> str:
    if conflict.symbol_name:
        return (
            f"Rebase after PR #{conflict.target_pr} merges, then resolve "
            f"the conflict in `{conflict.symbol_name}` in `{conflict.file_path}`."
        )
    return (
        f"Rebase after PR #{conflict.target_pr} merges. Both PRs modify "
        f"`{conflict.file_path}` at overlapping lines — resolve merge markers "
        f"and verify combined changes."
    )


def _behavioral_suggestion(conflict: Conflict) -> str:
    name = conflict.symbol_name or ""
    if "\u2192" in name:
        # Caller/callee relationship detected
        return (
            f"PRs #{conflict.source_pr} and #{conflict.target_pr} modify functions "
            f"with a caller/callee relationship (`{name}`) in "
            f"`{conflict.file_path}`. Test end-to-end with both changes."
        )
    return (
        f"Both PRs modify `{name}` in `{conflict.file_path}` at different lines. "
        f"Review PR #{conflict.target_pr}'s changes and run integration tests "
        f"covering `{name}` with both changesets."
    )


def _interface_suggestion(conflict: Conflict) -> str:
    return (
        f"PR #{conflict.target_pr} calls `{conflict.symbol_name}` with the old "
        f"signature. Coordinate to update the call site in `{conflict.file_path}`, "
        f"or add a backward-compatible overload."
    )


def _duplication_suggestion(conflict: Conflict) -> str:
    if conflict.symbol_name:
        return (
            f"`{conflict.symbol_name}` may duplicate functionality from "
            f"PR #{conflict.target_pr}. Check if you can reuse their "
            f"implementation instead."
        )
    return (
        f"PR #{conflict.target_pr} may be solving the same problem. "
        f"Coordinate to avoid duplicate work."
    )


def _transitive_suggestion(conflict: Conflict) -> str:
    base = (
        f"Your changes depend on `{conflict.file_path}` which is modified "
        f"by PR #{conflict.target_pr}. Verify compatibility after it merges."
    )
    if conflict.symbol_name:
        base += f" Specifically check `{conflict.symbol_name}`."
    return base


def _regression_suggestion(conflict: Conflict) -> str:
    if conflict.symbol_name:
        return (
            f"This change may revert a deliberate decision from "
            f"PR #{conflict.target_pr} affecting `{conflict.symbol_name}` "
            f"in `{conflict.file_path}`. Confirm this is intentional."
        )
    return (
        f"This change may revert a deliberate decision from "
        f"PR #{conflict.target_pr} in `{conflict.file_path}`. "
        f"Confirm this is intentional."
    )


def _secret_suggestion(conflict: Conflict) -> str:
    return (
        f"Rotate the exposed credential detected in `{conflict.file_path}` immediately. "
        f"Move the value to environment variables or a secrets manager, "
        f"then update references."
    )


def _guardrail_suggestion(conflict: Conflict) -> str:
    return (
        f"This PR violates a repository guardrail rule in "
        f"`{conflict.file_path}`. Adjust your changes or request an exception."
    )


_GENERATORS = {
    ConflictType.HARD: _hard_suggestion,
    ConflictType.BEHAVIORAL: _behavioral_suggestion,
    ConflictType.INTERFACE: _interface_suggestion,
    ConflictType.DUPLICATION: _duplication_suggestion,
    ConflictType.TRANSITIVE: _transitive_suggestion,
    ConflictType.REGRESSION: _regression_suggestion,
    ConflictType.SECRET: _secret_suggestion,
    ConflictType.GUARDRAIL: _guardrail_suggestion,
}


def generate_template_suggestion(conflict: Conflict) -> str | None:
    """Generate a template-based fix suggestion from conflict metadata.

    Returns a contextual suggestion string, or None if the conflict type
    is not recognized.
    """
    generator = _GENERATORS.get(conflict.conflict_type)
    if generator is None:
        return None
    return generator(conflict)
