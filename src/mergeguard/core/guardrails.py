"""Guardrails engine for .mergeguard.yml rule enforcement (V2).

Enforces repository-specific rules defined in .mergeguard.yml,
such as dependency rules, pattern rules, and AI-specific rules.
Planned for Phase 3 (Weeks 13-14).
"""

from __future__ import annotations

import fnmatch

from mergeguard.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    GuardrailRule,
    MergeGuardConfig,
    PRInfo,
)


def enforce_guardrails(
    pr: PRInfo,
    config: MergeGuardConfig,
) -> list[Conflict]:
    """Enforce all guardrail rules against a PR.

    Args:
        pr: The PR to check.
        config: Configuration containing guardrail rules.

    Returns:
        List of guardrail violations as Conflict objects.
    """
    violations: list[Conflict] = []

    for rule in config.rules:
        # Check if the rule applies based on conditions
        if rule.when == "ai_authored" and not pr.ai_attribution.value.startswith("ai"):
            continue

        rule_violations = _check_rule(pr, rule)
        violations.extend(rule_violations)

    return violations


def _check_rule(pr: PRInfo, rule: GuardrailRule) -> list[Conflict]:
    """Check a single guardrail rule against a PR."""
    violations: list[Conflict] = []

    # Check file-scoped rules
    matching_files = _get_matching_files(pr, rule.pattern)

    # Check size limits
    if rule.max_files_changed is not None:
        if len(pr.changed_files) > rule.max_files_changed:
            violations.append(
                Conflict(
                    conflict_type=ConflictType.REGRESSION,
                    severity=ConflictSeverity.WARNING,
                    source_pr=pr.number,
                    target_pr=pr.number,
                    file_path="<repo>",
                    description=(
                        f"PR changes {len(pr.changed_files)} files, "
                        f"exceeding the limit of {rule.max_files_changed}. "
                        f"Rule: {rule.name}"
                    ),
                    recommendation=rule.message or "Consider splitting this PR.",
                )
            )

    if rule.max_lines_changed is not None:
        total_lines = sum(
            f.additions + f.deletions for f in pr.changed_files
        )
        if total_lines > rule.max_lines_changed:
            violations.append(
                Conflict(
                    conflict_type=ConflictType.REGRESSION,
                    severity=ConflictSeverity.WARNING,
                    source_pr=pr.number,
                    target_pr=pr.number,
                    file_path="<repo>",
                    description=(
                        f"PR changes {total_lines} lines, "
                        f"exceeding the limit of {rule.max_lines_changed}. "
                        f"Rule: {rule.name}"
                    ),
                    recommendation=rule.message or "Consider splitting this PR.",
                )
            )

    return violations


def _get_matching_files(pr: PRInfo, pattern: str | None) -> list[str]:
    """Get files in the PR that match the rule's pattern."""
    if pattern is None:
        return [f.path for f in pr.changed_files]
    return [
        f.path for f in pr.changed_files if fnmatch.fnmatch(f.path, pattern)
    ]
