"""Policy engine for declarative conditions-and-actions evaluation.

Evaluates ConflictReport results against user-defined policies
in `.mergeguard.yml` and dispatches actions (block merge, add labels,
notify Slack, etc.).
"""

from __future__ import annotations

import fnmatch
import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from mergeguard.models import (
    AIAttribution,
    ConflictSeverity,
    PolicyActionType,
    PolicyConditionOp,
    PolicyConfig,
    PolicyEvaluationResult,
    PolicyResult,
)

if TYPE_CHECKING:
    from mergeguard.models import ConflictReport, PolicyAction, PolicyCondition, PolicyRule

logger = logging.getLogger(__name__)

# ── Field extractors ────────────────────────────────────────────────

FieldExtractor = Callable[["ConflictReport"], Any]


def _extract_risk_score(report: ConflictReport) -> float:
    return report.risk_score


def _extract_conflict_count(report: ConflictReport) -> int:
    return len(report.conflicts)


def _extract_critical_count(report: ConflictReport) -> int:
    return sum(1 for c in report.conflicts if c.severity == ConflictSeverity.CRITICAL)


def _extract_warning_count(report: ConflictReport) -> int:
    return sum(1 for c in report.conflicts if c.severity == ConflictSeverity.WARNING)


def _extract_has_severity(report: ConflictReport) -> set[str]:
    return {c.severity.value for c in report.conflicts}


def _extract_has_conflict_type(report: ConflictReport) -> set[str]:
    return {c.conflict_type.value for c in report.conflicts}


def _extract_affected_teams(report: ConflictReport) -> set[str]:
    return set(report.affected_teams)


def _extract_ai_authored(report: ConflictReport) -> bool:
    return report.pr.ai_attribution in (AIAttribution.AI_CONFIRMED, AIAttribution.AI_SUSPECTED)


def _extract_files_changed(report: ConflictReport) -> list[str]:
    return [f.path for f in report.pr.changed_files]


def _extract_labels(report: ConflictReport) -> set[str]:
    return set(report.pr.labels)


def _extract_author(report: ConflictReport) -> str:
    return report.pr.author


def _extract_file_count(report: ConflictReport) -> int:
    return len(report.pr.changed_files)


def _extract_lines_changed(report: ConflictReport) -> int:
    return sum(f.additions + f.deletions for f in report.pr.changed_files)


_FIELD_EXTRACTORS: dict[str, FieldExtractor] = {
    "risk_score": _extract_risk_score,
    "conflict_count": _extract_conflict_count,
    "critical_count": _extract_critical_count,
    "warning_count": _extract_warning_count,
    "has_severity": _extract_has_severity,
    "has_conflict_type": _extract_has_conflict_type,
    "affected_teams": _extract_affected_teams,
    "ai_authored": _extract_ai_authored,
    "files_changed": _extract_files_changed,
    "labels": _extract_labels,
    "author": _extract_author,
    "file_count": _extract_file_count,
    "lines_changed": _extract_lines_changed,
}


def extract_field(report: ConflictReport, field: str) -> Any:
    """Extract a field value from a ConflictReport.

    Returns None for unknown fields.
    """
    extractor = _FIELD_EXTRACTORS.get(field)
    if extractor is None:
        logger.warning("Unknown policy field: %s", field)
        return None
    return extractor(report)


# ── Condition evaluation ────────────────────────────────────────────


def _evaluate_condition(actual: Any, condition: PolicyCondition) -> bool:
    """Evaluate a single condition against an actual value."""
    if actual is None:
        return False

    op = condition.operator
    expected = condition.value

    if op == PolicyConditionOp.GTE:
        return bool(actual >= expected)
    elif op == PolicyConditionOp.LTE:
        return bool(actual <= expected)
    elif op == PolicyConditionOp.GT:
        return bool(actual > expected)
    elif op == PolicyConditionOp.LT:
        return bool(actual < expected)
    elif op == PolicyConditionOp.EQ:
        return bool(actual == expected)
    elif op == PolicyConditionOp.CONTAINS:
        # For set fields: check if value is in the set
        if isinstance(actual, (set, list, frozenset)):
            return expected in actual
        return False
    elif op == PolicyConditionOp.MATCHES:
        # Glob pattern matching on file paths (list of strings)
        if isinstance(actual, (list, set)):
            return any(fnmatch.fnmatch(item, expected) for item in actual)
        if isinstance(actual, str):
            return fnmatch.fnmatch(actual, expected)
        return False

    return False


# ── Policy evaluation ───────────────────────────────────────────────


def _evaluate_rule(report: ConflictReport, rule: PolicyRule) -> PolicyResult:
    """Evaluate a single policy rule against a report."""
    conditions_evaluated: list[dict[str, Any]] = []
    all_matched = True

    for condition in rule.conditions:
        actual = extract_field(report, condition.field)
        matched = _evaluate_condition(actual, condition)
        conditions_evaluated.append(
            {
                "field": condition.field,
                "operator": condition.operator.value,
                "expected": condition.value,
                "actual": actual if not isinstance(actual, set) else sorted(actual),
                "matched": matched,
            }
        )
        if not matched:
            all_matched = False

    return PolicyResult(
        policy_name=rule.name,
        matched=all_matched,
        conditions_evaluated=conditions_evaluated,
        actions_to_execute=list(rule.actions) if all_matched else [],
    )


def evaluate_policies(
    report: ConflictReport,
    config: PolicyConfig,
) -> PolicyEvaluationResult:
    """Evaluate all policy rules against a conflict report.

    Args:
        report: The conflict report to evaluate.
        config: Policy configuration with rules.

    Returns:
        PolicyEvaluationResult with matched policies and accumulated actions.
    """
    if not config.enabled:
        return PolicyEvaluationResult(evaluated_at=datetime.now(tz=None))

    results: list[PolicyResult] = []
    all_actions: list[PolicyAction] = []

    for rule in config.policies:
        if not rule.enabled:
            results.append(
                PolicyResult(
                    policy_name=rule.name,
                    matched=False,
                    conditions_evaluated=[],
                    actions_to_execute=[],
                )
            )
            continue

        result = _evaluate_rule(report, rule)
        results.append(result)
        if result.matched:
            all_actions.extend(result.actions_to_execute)

    return PolicyEvaluationResult(
        results=results,
        actions=all_actions,
        evaluated_at=datetime.now(tz=None),
    )


# ── Action execution ────────────────────────────────────────────────


def _render_policy_comment(
    report: ConflictReport,
    evaluation: PolicyEvaluationResult,
) -> str:
    """Render a markdown comment summarizing policy evaluation results."""
    lines: list[str] = [
        "<!-- mergeguard-policy -->",
        "## MergeGuard Policy Evaluation",
        "",
    ]

    matched = evaluation.matched_policies
    if matched:
        lines.append(f"**{len(matched)} policy/policies triggered:**")
        lines.append("")
        for result in evaluation.results:
            if result.matched:
                actions_str = ", ".join(a.action.value for a in result.actions_to_execute)
                lines.append(f"- **{result.policy_name}** → {actions_str}")
        lines.append("")
    else:
        lines.append("No policies triggered.")
        lines.append("")

    if evaluation.has_block:
        lines.append("> **Merge blocked** by policy engine.")
        lines.append("")

    # Action summary
    action_types = {a.action.value for a in evaluation.actions}
    if action_types:
        lines.append(f"Actions: {', '.join(sorted(action_types))}")

    return "\n".join(lines)


def execute_policy_actions(
    report: ConflictReport,
    evaluation: PolicyEvaluationResult,
    client: Any,
    repo: str,
    platform: str = "github",
) -> list[dict[str, Any]]:
    """Execute all actions from a policy evaluation.

    Args:
        report: The conflict report.
        evaluation: Policy evaluation result with actions.
        client: SCM client for API calls.
        repo: Repository name (owner/repo).
        platform: SCM platform name.

    Returns:
        Execution log — list of dicts with action type, success, and details.
    """
    log: list[dict[str, Any]] = []

    for action in evaluation.actions:
        entry: dict[str, Any] = {"action": action.action.value, "success": False}
        try:
            if action.action == PolicyActionType.BLOCK_MERGE:
                msg = action.message or "Blocked by MergeGuard policy"
                client.post_commit_status(
                    sha=report.pr.head_sha,
                    state="failure",
                    description=msg[:140],
                    context=action.status_context,
                )
                entry["success"] = True

            elif action.action == PolicyActionType.SET_STATUS:
                client.post_commit_status(
                    sha=report.pr.head_sha,
                    state=action.status_state,
                    description=action.message[:140] if action.message else "Policy status",
                    context=action.status_context,
                )
                entry["success"] = True

            elif action.action == PolicyActionType.POST_COMMENT:
                comment = _render_policy_comment(report, evaluation)
                client.post_pr_comment(report.pr.number, comment)
                entry["success"] = True

            elif action.action == PolicyActionType.ADD_LABELS:
                if hasattr(client, "add_labels"):
                    client.add_labels(report.pr.number, action.labels)
                    entry["success"] = True
                else:
                    entry["detail"] = "Client does not support add_labels"
                    logger.warning("Client %s does not support add_labels", type(client).__name__)

            elif action.action == PolicyActionType.REQUIRE_REVIEWERS:
                if hasattr(client, "request_reviewers"):
                    client.request_reviewers(report.pr.number, action.reviewers)
                    entry["success"] = True
                else:
                    entry["detail"] = "Client does not support request_reviewers"
                    logger.warning(
                        "Client %s does not support request_reviewers",
                        type(client).__name__,
                    )

            elif action.action == PolicyActionType.NOTIFY_SLACK:
                from mergeguard.output.notifications import notify_slack

                result = notify_slack(action.webhook_url, report, repo)
                entry["success"] = result

            elif action.action == PolicyActionType.NOTIFY_TEAMS:
                from mergeguard.output.notifications import notify_teams

                result = notify_teams(action.webhook_url, report, repo)
                entry["success"] = result

        except Exception:
            logger.warning("Policy action %s failed", action.action.value, exc_info=True)
            entry["error"] = True

        log.append(entry)

    return log
