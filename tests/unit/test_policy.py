"""Tests for the policy engine — field extraction, condition evaluation,
policy matching, action execution, and SCM client methods."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from mergeguard.core.policy import (
    _evaluate_condition,
    evaluate_policies,
    execute_policy_actions,
    extract_field,
)
from mergeguard.models import (
    AIAttribution,
    ChangedFile,
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    FileChangeStatus,
    PolicyAction,
    PolicyActionType,
    PolicyCondition,
    PolicyConditionOp,
    PolicyConfig,
    PolicyEvaluationResult,
    PolicyResult,
    PolicyRule,
    PRInfo,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_pr(
    number: int = 42,
    labels: list[str] | None = None,
    author: str = "alice",
    ai_attribution: AIAttribution = AIAttribution.UNKNOWN,
    changed_files: list[ChangedFile] | None = None,
) -> PRInfo:
    now = datetime.now(UTC)
    return PRInfo(
        number=number,
        title=f"PR #{number}",
        author=author,
        base_branch="main",
        head_branch=f"feature-{number}",
        head_sha=f"sha{number}",
        created_at=now,
        updated_at=now,
        labels=labels or [],
        ai_attribution=ai_attribution,
        changed_files=changed_files or [],
    )


def _make_conflict(
    source_pr: int = 42,
    target_pr: int = 99,
    severity: ConflictSeverity = ConflictSeverity.CRITICAL,
    conflict_type: ConflictType = ConflictType.HARD,
    owners: list[str] | None = None,
) -> Conflict:
    return Conflict(
        conflict_type=conflict_type,
        severity=severity,
        source_pr=source_pr,
        target_pr=target_pr,
        file_path="src/main.py",
        description="Test conflict",
        recommendation="Fix it",
        owners=owners or [],
    )


def _make_report(
    pr_number: int = 42,
    conflicts: list[Conflict] | None = None,
    risk_score: float = 0.0,
    labels: list[str] | None = None,
    author: str = "alice",
    ai_attribution: AIAttribution = AIAttribution.UNKNOWN,
    affected_teams: list[str] | None = None,
    changed_files: list[ChangedFile] | None = None,
) -> ConflictReport:
    return ConflictReport(
        pr=_make_pr(
            number=pr_number,
            labels=labels,
            author=author,
            ai_attribution=ai_attribution,
            changed_files=changed_files,
        ),
        conflicts=conflicts or [],
        risk_score=risk_score,
        affected_teams=affected_teams or [],
    )


def _make_changed_file(path: str, additions: int = 10, deletions: int = 5) -> ChangedFile:
    return ChangedFile(
        path=path,
        status=FileChangeStatus.MODIFIED,
        additions=additions,
        deletions=deletions,
    )


def _make_rule(
    name: str = "test-rule",
    conditions: list[PolicyCondition] | None = None,
    actions: list[PolicyAction] | None = None,
    enabled: bool = True,
) -> PolicyRule:
    return PolicyRule(
        name=name,
        conditions=conditions or [],
        actions=actions or [PolicyAction(action=PolicyActionType.BLOCK_MERGE)],
        enabled=enabled,
    )


def _make_config(
    enabled: bool = True,
    policies: list[PolicyRule] | None = None,
) -> PolicyConfig:
    return PolicyConfig(enabled=enabled, policies=policies or [])


# ═══════════════════════════════════════════════════════════════════════
# Field Extraction Tests
# ═══════════════════════════════════════════════════════════════════════


class TestFieldExtraction:
    def test_risk_score(self):
        report = _make_report(risk_score=75.5)
        assert extract_field(report, "risk_score") == 75.5

    def test_conflict_count(self):
        report = _make_report(conflicts=[_make_conflict(), _make_conflict(target_pr=100)])
        assert extract_field(report, "conflict_count") == 2

    def test_critical_count(self):
        report = _make_report(
            conflicts=[
                _make_conflict(severity=ConflictSeverity.CRITICAL),
                _make_conflict(severity=ConflictSeverity.WARNING, target_pr=100),
                _make_conflict(severity=ConflictSeverity.CRITICAL, target_pr=101),
            ]
        )
        assert extract_field(report, "critical_count") == 2

    def test_warning_count(self):
        report = _make_report(
            conflicts=[
                _make_conflict(severity=ConflictSeverity.WARNING),
                _make_conflict(severity=ConflictSeverity.WARNING, target_pr=100),
                _make_conflict(severity=ConflictSeverity.INFO, target_pr=101),
            ]
        )
        assert extract_field(report, "warning_count") == 2

    def test_has_severity(self):
        report = _make_report(
            conflicts=[
                _make_conflict(severity=ConflictSeverity.CRITICAL),
                _make_conflict(severity=ConflictSeverity.WARNING, target_pr=100),
            ]
        )
        result = extract_field(report, "has_severity")
        assert result == {"critical", "warning"}

    def test_has_conflict_type(self):
        report = _make_report(
            conflicts=[
                _make_conflict(conflict_type=ConflictType.HARD),
                _make_conflict(conflict_type=ConflictType.INTERFACE, target_pr=100),
            ]
        )
        result = extract_field(report, "has_conflict_type")
        assert result == {"hard", "interface"}

    def test_affected_teams(self):
        report = _make_report(affected_teams=["@frontend", "@backend"])
        result = extract_field(report, "affected_teams")
        assert result == {"@frontend", "@backend"}

    def test_ai_authored_true(self):
        report = _make_report(ai_attribution=AIAttribution.AI_CONFIRMED)
        assert extract_field(report, "ai_authored") is True

    def test_ai_authored_suspected(self):
        report = _make_report(ai_attribution=AIAttribution.AI_SUSPECTED)
        assert extract_field(report, "ai_authored") is True

    def test_ai_authored_false(self):
        report = _make_report(ai_attribution=AIAttribution.HUMAN)
        assert extract_field(report, "ai_authored") is False

    def test_ai_authored_unknown(self):
        report = _make_report(ai_attribution=AIAttribution.UNKNOWN)
        assert extract_field(report, "ai_authored") is False

    def test_files_changed(self):
        files = [_make_changed_file("src/a.py"), _make_changed_file("src/b.py")]
        report = _make_report(changed_files=files)
        assert extract_field(report, "files_changed") == ["src/a.py", "src/b.py"]

    def test_labels(self):
        report = _make_report(labels=["bug", "high-priority"])
        assert extract_field(report, "labels") == {"bug", "high-priority"}

    def test_author(self):
        report = _make_report(author="bob")
        assert extract_field(report, "author") == "bob"

    def test_file_count(self):
        files = [_make_changed_file(f"src/{i}.py") for i in range(3)]
        report = _make_report(changed_files=files)
        assert extract_field(report, "file_count") == 3

    def test_lines_changed(self):
        files = [
            _make_changed_file("a.py", additions=10, deletions=5),
            _make_changed_file("b.py", additions=20, deletions=3),
        ]
        report = _make_report(changed_files=files)
        assert extract_field(report, "lines_changed") == 38

    def test_unknown_field_returns_none(self):
        report = _make_report()
        assert extract_field(report, "nonexistent_field") is None


# ═══════════════════════════════════════════════════════════════════════
# Condition Evaluation Tests
# ═══════════════════════════════════════════════════════════════════════


class TestConditionEvaluation:
    def test_gte_pass(self):
        cond = PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=50)
        assert _evaluate_condition(75, cond) is True

    def test_gte_exact(self):
        cond = PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=50)
        assert _evaluate_condition(50, cond) is True

    def test_gte_fail(self):
        cond = PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=50)
        assert _evaluate_condition(49, cond) is False

    def test_lte_pass(self):
        cond = PolicyCondition(field="risk_score", operator=PolicyConditionOp.LTE, value=50)
        assert _evaluate_condition(30, cond) is True

    def test_lte_fail(self):
        cond = PolicyCondition(field="risk_score", operator=PolicyConditionOp.LTE, value=50)
        assert _evaluate_condition(51, cond) is False

    def test_gt_pass(self):
        cond = PolicyCondition(field="x", operator=PolicyConditionOp.GT, value=10)
        assert _evaluate_condition(11, cond) is True

    def test_gt_exact_fail(self):
        cond = PolicyCondition(field="x", operator=PolicyConditionOp.GT, value=10)
        assert _evaluate_condition(10, cond) is False

    def test_lt_pass(self):
        cond = PolicyCondition(field="x", operator=PolicyConditionOp.LT, value=10)
        assert _evaluate_condition(9, cond) is True

    def test_lt_exact_fail(self):
        cond = PolicyCondition(field="x", operator=PolicyConditionOp.LT, value=10)
        assert _evaluate_condition(10, cond) is False

    def test_eq_pass(self):
        cond = PolicyCondition(field="x", operator=PolicyConditionOp.EQ, value=True)
        assert _evaluate_condition(True, cond) is True

    def test_eq_fail(self):
        cond = PolicyCondition(field="x", operator=PolicyConditionOp.EQ, value=True)
        assert _evaluate_condition(False, cond) is False

    def test_eq_string(self):
        cond = PolicyCondition(field="author", operator=PolicyConditionOp.EQ, value="bob")
        assert _evaluate_condition("bob", cond) is True
        assert _evaluate_condition("alice", cond) is False

    def test_contains_set(self):
        cond = PolicyCondition(
            field="has_severity", operator=PolicyConditionOp.CONTAINS, value="critical"
        )
        assert _evaluate_condition({"critical", "warning"}, cond) is True

    def test_contains_not_in_set(self):
        cond = PolicyCondition(
            field="has_severity", operator=PolicyConditionOp.CONTAINS, value="critical"
        )
        assert _evaluate_condition({"warning", "info"}, cond) is False

    def test_contains_list(self):
        cond = PolicyCondition(
            field="labels", operator=PolicyConditionOp.CONTAINS, value="high-risk"
        )
        assert _evaluate_condition(["high-risk", "bug"], cond) is True

    def test_contains_non_collection(self):
        cond = PolicyCondition(field="x", operator=PolicyConditionOp.CONTAINS, value="a")
        assert _evaluate_condition(42, cond) is False

    def test_matches_glob_pass(self):
        cond = PolicyCondition(
            field="files_changed", operator=PolicyConditionOp.MATCHES, value="infra/**"
        )
        files = ["infra/terraform/main.tf", "src/app.py"]
        assert _evaluate_condition(files, cond) is True

    def test_matches_glob_fail(self):
        cond = PolicyCondition(
            field="files_changed", operator=PolicyConditionOp.MATCHES, value="infra/**"
        )
        files = ["src/app.py", "tests/test_app.py"]
        assert _evaluate_condition(files, cond) is False

    def test_matches_single_string(self):
        cond = PolicyCondition(field="author", operator=PolicyConditionOp.MATCHES, value="bot-*")
        assert _evaluate_condition("bot-deploy", cond) is True
        assert _evaluate_condition("alice", cond) is False

    def test_none_actual_returns_false(self):
        cond = PolicyCondition(field="x", operator=PolicyConditionOp.GTE, value=10)
        assert _evaluate_condition(None, cond) is False


# ═══════════════════════════════════════════════════════════════════════
# Policy Evaluation Tests
# ═══════════════════════════════════════════════════════════════════════


class TestPolicyEvaluation:
    def test_disabled_config_returns_empty(self):
        config = _make_config(enabled=False, policies=[_make_rule()])
        report = _make_report()
        result = evaluate_policies(report, config)
        assert result.results == []
        assert result.actions == []

    def test_empty_policies(self):
        config = _make_config(enabled=True, policies=[])
        report = _make_report()
        result = evaluate_policies(report, config)
        assert result.results == []
        assert result.actions == []

    def test_single_policy_match(self):
        rule = _make_rule(
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=50)
            ],
            actions=[PolicyAction(action=PolicyActionType.BLOCK_MERGE, message="Blocked")],
        )
        config = _make_config(policies=[rule])
        report = _make_report(risk_score=80)
        result = evaluate_policies(report, config)

        assert len(result.results) == 1
        assert result.results[0].matched is True
        assert len(result.actions) == 1
        assert result.actions[0].action == PolicyActionType.BLOCK_MERGE

    def test_single_policy_no_match(self):
        rule = _make_rule(
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=90)
            ],
        )
        config = _make_config(policies=[rule])
        report = _make_report(risk_score=50)
        result = evaluate_policies(report, config)

        assert result.results[0].matched is False
        assert result.actions == []

    def test_multiple_conditions_and_all_match(self):
        rule = _make_rule(
            name="block-critical-ai",
            conditions=[
                PolicyCondition(field="ai_authored", operator=PolicyConditionOp.EQ, value=True),
                PolicyCondition(
                    field="has_severity",
                    operator=PolicyConditionOp.CONTAINS,
                    value="critical",
                ),
            ],
        )
        config = _make_config(policies=[rule])
        report = _make_report(
            ai_attribution=AIAttribution.AI_CONFIRMED,
            conflicts=[_make_conflict(severity=ConflictSeverity.CRITICAL)],
        )
        result = evaluate_policies(report, config)
        assert result.results[0].matched is True

    def test_multiple_conditions_and_partial_no_fire(self):
        rule = _make_rule(
            conditions=[
                PolicyCondition(field="ai_authored", operator=PolicyConditionOp.EQ, value=True),
                PolicyCondition(
                    field="has_severity",
                    operator=PolicyConditionOp.CONTAINS,
                    value="critical",
                ),
            ],
        )
        config = _make_config(policies=[rule])
        # AI authored but no critical severity
        report = _make_report(
            ai_attribution=AIAttribution.AI_CONFIRMED,
            conflicts=[_make_conflict(severity=ConflictSeverity.WARNING)],
        )
        result = evaluate_policies(report, config)
        assert result.results[0].matched is False

    def test_multiple_policies_independent(self):
        rule_a = _make_rule(
            name="rule-a",
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=80)
            ],
            actions=[PolicyAction(action=PolicyActionType.ADD_LABELS, labels=["high-risk"])],
        )
        rule_b = _make_rule(
            name="rule-b",
            conditions=[
                PolicyCondition(field="conflict_count", operator=PolicyConditionOp.GTE, value=1)
            ],
            actions=[PolicyAction(action=PolicyActionType.POST_COMMENT)],
        )
        config = _make_config(policies=[rule_a, rule_b])
        report = _make_report(
            risk_score=90,
            conflicts=[_make_conflict()],
        )
        result = evaluate_policies(report, config)

        assert result.results[0].matched is True
        assert result.results[1].matched is True
        assert len(result.actions) == 2

    def test_disabled_policy_skipped(self):
        rule = _make_rule(
            name="disabled-rule",
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=0)
            ],
            enabled=False,
        )
        config = _make_config(policies=[rule])
        report = _make_report(risk_score=100)
        result = evaluate_policies(report, config)

        assert result.results[0].matched is False
        assert result.actions == []

    def test_audit_trail_details(self):
        rule = _make_rule(
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=50),
                PolicyCondition(field="conflict_count", operator=PolicyConditionOp.GTE, value=3),
            ],
        )
        config = _make_config(policies=[rule])
        report = _make_report(risk_score=80, conflicts=[_make_conflict()])
        result = evaluate_policies(report, config)

        # First condition matches, second doesn't
        evals = result.results[0].conditions_evaluated
        assert len(evals) == 2
        assert evals[0]["field"] == "risk_score"
        assert evals[0]["matched"] is True
        assert evals[0]["actual"] == 80.0
        assert evals[1]["field"] == "conflict_count"
        assert evals[1]["matched"] is False
        assert evals[1]["actual"] == 1

    def test_has_block_property(self):
        rule = _make_rule(
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=0)
            ],
            actions=[PolicyAction(action=PolicyActionType.BLOCK_MERGE)],
        )
        config = _make_config(policies=[rule])
        report = _make_report(risk_score=50)
        result = evaluate_policies(report, config)
        assert result.has_block is True

    def test_has_block_false(self):
        rule = _make_rule(
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=0)
            ],
            actions=[PolicyAction(action=PolicyActionType.ADD_LABELS, labels=["test"])],
        )
        config = _make_config(policies=[rule])
        report = _make_report(risk_score=50)
        result = evaluate_policies(report, config)
        assert result.has_block is False

    def test_matched_policies_property(self):
        rule_a = _make_rule(
            name="match-a",
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=0)
            ],
        )
        rule_b = _make_rule(
            name="no-match-b",
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=999)
            ],
        )
        config = _make_config(policies=[rule_a, rule_b])
        report = _make_report(risk_score=50)
        result = evaluate_policies(report, config)
        assert result.matched_policies == ["match-a"]

    def test_actions_accumulated_across_policies(self):
        rule_a = _make_rule(
            name="rule-a",
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=0)
            ],
            actions=[
                PolicyAction(action=PolicyActionType.BLOCK_MERGE),
                PolicyAction(action=PolicyActionType.ADD_LABELS, labels=["blocked"]),
            ],
        )
        rule_b = _make_rule(
            name="rule-b",
            conditions=[
                PolicyCondition(field="risk_score", operator=PolicyConditionOp.GTE, value=0)
            ],
            actions=[PolicyAction(action=PolicyActionType.POST_COMMENT)],
        )
        config = _make_config(policies=[rule_a, rule_b])
        report = _make_report(risk_score=50)
        result = evaluate_policies(report, config)
        assert len(result.actions) == 3


# ═══════════════════════════════════════════════════════════════════════
# Action Execution Tests
# ═══════════════════════════════════════════════════════════════════════


class TestActionExecution:
    def _make_evaluation(self, actions: list[PolicyAction]) -> PolicyEvaluationResult:
        return PolicyEvaluationResult(
            results=[
                PolicyResult(
                    policy_name="test",
                    matched=True,
                    actions_to_execute=actions,
                )
            ],
            actions=actions,
            evaluated_at=datetime.now(tz=None),
        )

    def test_block_merge_calls_post_commit_status(self):
        client = MagicMock()
        action = PolicyAction(
            action=PolicyActionType.BLOCK_MERGE,
            message="Blocked by policy",
        )
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        client.post_commit_status.assert_called_once()
        call_kwargs = client.post_commit_status.call_args
        assert call_kwargs.kwargs["state"] == "failure"
        assert log[0]["success"] is True

    def test_set_status_calls_post_commit_status(self):
        client = MagicMock()
        action = PolicyAction(
            action=PolicyActionType.SET_STATUS,
            status_state="success",
            status_context="custom/context",
            message="All good",
        )
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        call_kwargs = client.post_commit_status.call_args
        assert call_kwargs.kwargs["state"] == "success"
        assert call_kwargs.kwargs["context"] == "custom/context"
        assert log[0]["success"] is True

    def test_post_comment_calls_post_pr_comment(self):
        client = MagicMock()
        action = PolicyAction(action=PolicyActionType.POST_COMMENT)
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        client.post_pr_comment.assert_called_once()
        body = client.post_pr_comment.call_args[0][1]
        assert "Policy Evaluation" in body
        assert log[0]["success"] is True

    def test_add_labels_with_support(self):
        client = MagicMock()
        action = PolicyAction(
            action=PolicyActionType.ADD_LABELS, labels=["high-risk", "needs-review"]
        )
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        client.add_labels.assert_called_once_with(42, ["high-risk", "needs-review"])
        assert log[0]["success"] is True

    def test_add_labels_graceful_without_support(self):
        client = MagicMock(spec=[])  # No methods
        action = PolicyAction(action=PolicyActionType.ADD_LABELS, labels=["test"])
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        assert log[0]["success"] is False
        assert "does not support" in log[0].get("detail", "")

    def test_require_reviewers_with_support(self):
        client = MagicMock()
        action = PolicyAction(
            action=PolicyActionType.REQUIRE_REVIEWERS,
            reviewers=["@platform-team", "bob"],
        )
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        client.request_reviewers.assert_called_once_with(42, ["@platform-team", "bob"])
        assert log[0]["success"] is True

    def test_require_reviewers_graceful_without_support(self):
        client = MagicMock(spec=[])
        action = PolicyAction(
            action=PolicyActionType.REQUIRE_REVIEWERS,
            reviewers=["@team"],
        )
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        assert log[0]["success"] is False

    @patch("mergeguard.output.notifications.notify_slack", return_value=True)
    def test_notify_slack(self, mock_notify):
        client = MagicMock()
        action = PolicyAction(
            action=PolicyActionType.NOTIFY_SLACK,
            webhook_url="https://hooks.slack.com/test",
        )
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        mock_notify.assert_called_once()
        assert log[0]["success"] is True

    @patch("mergeguard.output.notifications.notify_teams", return_value=True)
    def test_notify_teams(self, mock_notify):
        client = MagicMock()
        action = PolicyAction(
            action=PolicyActionType.NOTIFY_TEAMS,
            webhook_url="https://outlook.webhook.office.com/test",
        )
        report = _make_report()
        evaluation = self._make_evaluation([action])

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        mock_notify.assert_called_once()
        assert log[0]["success"] is True

    def test_exception_in_one_action_does_not_block_others(self):
        client = MagicMock()
        client.post_commit_status.side_effect = RuntimeError("API error")

        actions = [
            PolicyAction(action=PolicyActionType.BLOCK_MERGE),
            PolicyAction(action=PolicyActionType.ADD_LABELS, labels=["test"]),
        ]
        report = _make_report()
        evaluation = self._make_evaluation(actions)

        log = execute_policy_actions(report, evaluation, client, "owner/repo")

        # First action failed, second succeeded
        assert len(log) == 2
        assert log[0].get("error") is True
        assert log[1]["success"] is True

    def test_empty_actions(self):
        client = MagicMock()
        evaluation = self._make_evaluation([])
        report = _make_report()

        log = execute_policy_actions(report, evaluation, client, "owner/repo")
        assert log == []


# ═══════════════════════════════════════════════════════════════════════
# SCM Client Method Tests
# ═══════════════════════════════════════════════════════════════════════


class TestGitHubClientMethods:
    def test_add_labels(self):
        """GitHub add_labels calls issue.add_to_labels."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_issue

        # Simulate GitHubClient without real API
        from mergeguard.integrations.github_client import GitHubClient

        client = object.__new__(GitHubClient)
        client._repo = mock_repo

        client.add_labels(42, ["high-risk", "needs-review"])

        mock_repo.get_issue.assert_called_once_with(42)
        mock_issue.add_to_labels.assert_called_once_with("high-risk", "needs-review")

    def test_request_reviewers_users_and_teams(self):
        """GitHub request_reviewers splits users and teams."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr

        from mergeguard.integrations.github_client import GitHubClient

        client = object.__new__(GitHubClient)
        client._repo = mock_repo

        client.request_reviewers(42, ["alice", "@org/platform-team"])

        mock_repo.get_pull.assert_called_once_with(42)
        mock_pr.create_review_request.assert_called_once_with(
            reviewers=["alice"], team_reviewers=["org/platform-team"]
        )


class TestBitbucketClientLabels:
    def test_add_labels_logs_warning(self, caplog):
        """Bitbucket add_labels is a no-op that logs a warning."""
        from mergeguard.integrations.bitbucket_client import BitbucketClient

        client = object.__new__(BitbucketClient)

        import logging

        with caplog.at_level(logging.WARNING, logger="mergeguard.integrations.bitbucket_client"):
            client.add_labels(42, ["high-risk"])

        assert "does not support PR labels" in caplog.text


# ═══════════════════════════════════════════════════════════════════════
# Model Tests
# ═══════════════════════════════════════════════════════════════════════


class TestPolicyModels:
    def test_policy_evaluation_result_has_block(self):
        result = PolicyEvaluationResult(
            actions=[PolicyAction(action=PolicyActionType.BLOCK_MERGE)],
            evaluated_at=datetime.now(tz=None),
        )
        assert result.has_block is True

    def test_policy_evaluation_result_no_block(self):
        result = PolicyEvaluationResult(
            actions=[PolicyAction(action=PolicyActionType.ADD_LABELS, labels=["x"])],
            evaluated_at=datetime.now(tz=None),
        )
        assert result.has_block is False

    def test_policy_evaluation_result_empty(self):
        result = PolicyEvaluationResult(evaluated_at=datetime.now(tz=None))
        assert result.has_block is False
        assert result.matched_policies == []

    def test_policy_config_defaults(self):
        config = PolicyConfig()
        assert config.enabled is False
        assert config.policies == []

    def test_mergeguard_config_has_policy(self):
        from mergeguard.models import MergeGuardConfig

        cfg = MergeGuardConfig()
        assert cfg.policy.enabled is False
