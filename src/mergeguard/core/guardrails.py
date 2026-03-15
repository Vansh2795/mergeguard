"""Guardrails engine for .mergeguard.yml rule enforcement.

Enforces repository-specific rules defined in .mergeguard.yml,
such as dependency rules, pattern rules, and AI-specific rules.
"""

from __future__ import annotations

import fnmatch
import logging

from mergeguard.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    GuardrailRule,
    MergeGuardConfig,
    PRInfo,
)

logger = logging.getLogger(__name__)


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

    # Check file-scoped rules — use only files matching the rule pattern
    matching_files = _get_matching_files(pr, rule.pattern)

    # Check size limits against matching files only
    if rule.max_files_changed is not None and len(matching_files) > rule.max_files_changed:
        violations.append(
            Conflict(
                conflict_type=ConflictType.GUARDRAIL,
                severity=ConflictSeverity.WARNING,
                source_pr=pr.number,
                target_pr=pr.number,
                file_path="<repo>",
                description=(
                    f"PR changes {len(matching_files)} matching files, "
                    f"exceeding the limit of {rule.max_files_changed}. "
                    f"Rule: {rule.name}"
                ),
                recommendation=rule.message or "Consider splitting this PR.",
            )
        )

    if rule.max_lines_changed is not None:
        matching_paths = set(matching_files)
        matching_cfs = [f for f in pr.changed_files if f.path in matching_paths]
        total_lines = sum(f.additions + f.deletions for f in matching_cfs)
        if total_lines > rule.max_lines_changed:
            violations.append(
                Conflict(
                    conflict_type=ConflictType.GUARDRAIL,
                    severity=ConflictSeverity.WARNING,
                    source_pr=pr.number,
                    target_pr=pr.number,
                    file_path="<repo>",
                    description=(
                        f"PR changes {total_lines} lines in matching files, "
                        f"exceeding the limit of {rule.max_lines_changed}. "
                        f"Rule: {rule.name}"
                    ),
                    recommendation=rule.message or "Consider splitting this PR.",
                )
            )

    # Check cannot_import_from
    if rule.cannot_import_from:
        violations.extend(_check_cannot_import_from(pr, rule, matching_files))

    # Check must_not_contain
    if rule.must_not_contain:
        violations.extend(_check_must_not_contain(pr, rule, matching_files))

    # Check max_function_lines
    if rule.max_function_lines is not None:
        violations.extend(_check_max_function_lines(pr, rule, matching_files))

    # Check max_cyclomatic_complexity
    if rule.max_cyclomatic_complexity is not None:
        violations.extend(_check_max_cyclomatic_complexity(pr, rule, matching_files))

    return violations


def _check_cannot_import_from(
    pr: PRInfo, rule: GuardrailRule, matching_files: list[str]
) -> list[Conflict]:
    """Check that matching files don't import from forbidden patterns."""
    from mergeguard.analysis.dependency import extract_imports

    violations: list[Conflict] = []
    for cf in pr.changed_files:
        if cf.path not in matching_files or not cf.patch:
            continue
        # Extract added lines from the patch
        added_lines = "\n".join(
            line[1:]
            for line in cf.patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        if not added_lines.strip():
            continue
        imports = extract_imports(added_lines, cf.path)
        for imp in imports:
            for forbidden in rule.cannot_import_from:
                if fnmatch.fnmatch(imp, forbidden) or fnmatch.fnmatch(
                    imp.replace(".", "/"), forbidden
                ):
                    violations.append(
                        Conflict(
                            conflict_type=ConflictType.GUARDRAIL,
                            severity=ConflictSeverity.WARNING,
                            source_pr=pr.number,
                            target_pr=pr.number,
                            file_path=cf.path,
                            symbol_name=imp,
                            description=(
                                f"`{cf.path}` imports `{imp}`, which is "
                                f"forbidden by rule '{rule.name}' "
                                f"(cannot_import_from: {forbidden})."
                            ),
                            recommendation=rule.message or f"Remove import of `{imp}`.",
                        )
                    )
    return violations


def _check_must_not_contain(
    pr: PRInfo, rule: GuardrailRule, matching_files: list[str]
) -> list[Conflict]:
    """Check that added lines don't contain forbidden strings."""
    violations: list[Conflict] = []
    matching_set = set(matching_files)
    for cf in pr.changed_files:
        if cf.path not in matching_set or not cf.patch:
            continue
        for _line_num, line in enumerate(cf.patch.splitlines(), 1):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            content = line[1:]
            for forbidden in rule.must_not_contain:
                if forbidden in content:
                    violations.append(
                        Conflict(
                            conflict_type=ConflictType.GUARDRAIL,
                            severity=ConflictSeverity.WARNING,
                            source_pr=pr.number,
                            target_pr=pr.number,
                            file_path=cf.path,
                            description=(
                                f"`{cf.path}` contains forbidden pattern "
                                f"`{forbidden}`. Rule: {rule.name}"
                            ),
                            recommendation=rule.message
                            or f"Remove or replace `{forbidden}`.",
                        )
                    )
                    break  # One violation per file per forbidden string is enough
    return violations


def _check_max_function_lines(
    pr: PRInfo, rule: GuardrailRule, matching_files: list[str]
) -> list[Conflict]:
    """Check that modified functions don't exceed the line limit."""
    violations: list[Conflict] = []
    matching_set = set(matching_files)
    max_lines = rule.max_function_lines
    assert max_lines is not None

    for cs in pr.changed_symbols:
        if cs.symbol.file_path not in matching_set:
            continue
        if cs.symbol.symbol_type.value not in ("function", "method"):
            continue
        func_lines = cs.symbol.end_line - cs.symbol.start_line + 1
        if func_lines > max_lines:
            violations.append(
                Conflict(
                    conflict_type=ConflictType.GUARDRAIL,
                    severity=ConflictSeverity.WARNING,
                    source_pr=pr.number,
                    target_pr=pr.number,
                    file_path=cs.symbol.file_path,
                    symbol_name=cs.symbol.name,
                    description=(
                        f"Function `{cs.symbol.name}` is {func_lines} lines "
                        f"(limit: {max_lines}). Rule: {rule.name}"
                    ),
                    recommendation=rule.message
                    or f"Refactor `{cs.symbol.name}` to be under {max_lines} lines.",
                )
            )
    return violations


def _check_max_cyclomatic_complexity(
    pr: PRInfo, rule: GuardrailRule, matching_files: list[str]
) -> list[Conflict]:
    """Check that modified functions don't exceed cyclomatic complexity limit."""
    from mergeguard.analysis.ast_parser import compute_cyclomatic_complexity

    violations: list[Conflict] = []
    matching_set = set(matching_files)
    max_complexity = rule.max_cyclomatic_complexity
    assert max_complexity is not None

    for cs in pr.changed_symbols:
        if cs.symbol.file_path not in matching_set:
            continue
        if cs.symbol.symbol_type.value not in ("function", "method"):
            continue
        if not cs.raw_diff:
            continue
        complexity = compute_cyclomatic_complexity(cs.raw_diff, cs.symbol.file_path)
        if complexity > max_complexity:
            violations.append(
                Conflict(
                    conflict_type=ConflictType.GUARDRAIL,
                    severity=ConflictSeverity.WARNING,
                    source_pr=pr.number,
                    target_pr=pr.number,
                    file_path=cs.symbol.file_path,
                    symbol_name=cs.symbol.name,
                    description=(
                        f"Function `{cs.symbol.name}` has cyclomatic complexity "
                        f"{complexity} (limit: {max_complexity}). Rule: {rule.name}"
                    ),
                    recommendation=rule.message
                    or f"Simplify `{cs.symbol.name}` to reduce branching.",
                )
            )
    return violations


def _get_matching_files(pr: PRInfo, pattern: str | None) -> list[str]:
    """Get files in the PR that match the rule's pattern."""
    if pattern is None:
        return [f.path for f in pr.changed_files]
    return [f.path for f in pr.changed_files if fnmatch.fnmatch(f.path, pattern)]
