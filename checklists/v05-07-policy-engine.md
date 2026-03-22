# v0.5 — Feature 07: Policy Engine

## Goals
- Provide a declarative policy language combining file patterns, PR metadata, conflict state, and team ownership into enforceable rules
- Go beyond current guardrails with richer semantics: cross-repo constraints, approval requirements, and conditional actions
- Generate an audit log of policy evaluations for enterprise compliance

## Daily Tasks

### Day 1-2: Policy Model & Parser
- [ ] Create `core/policy.py` module
- [ ] Define `Policy` Pydantic model: `name`, `when` (conditions dict), `require` (requirements dict), `action` (string), `message`
- [ ] Define `PolicyCondition` types: `files_match` (glob), `ai_authored` (bool), `lines_changed` (comparison), `conflicts_with_repo` (list), `labels` (list), `author_team` (string)
- [ ] Define `PolicyAction` types: `block_merge`, `request_review`, `add_label`, `notify_team`, `warn`
- [ ] Parse policies from `policies` section in `.mergeguard.yml`
- [ ] Validate policy syntax on config load with clear error messages

### Day 3: Policy Evaluation Engine
- [ ] Implement `evaluate_policies(pr: PRInfo, report: ConflictReport, policies: list[Policy]) -> list[PolicyResult]`
- [ ] Evaluate `when` conditions: match against PR metadata, changed files, conflict state, CODEOWNERS teams
- [ ] Evaluate `require` block: check approval counts (via SCM API), required labels, required reviewers
- [ ] Execute `action` block: map to concrete actions (set commit status, post comment, add label)
- [ ] Wire policy evaluation into `core/engine.py` after conflict analysis and CODEOWNERS resolution
- [ ] Generate `GUARDRAIL` conflicts for policy violations (reuse existing conflict type)

### Day 4: Actions & Audit Log
- [ ] Implement `block_merge` action: set commit status to `failure` with policy name in description
- [ ] Implement `request_review` action: use GitHub API to request review from specified team/user
- [ ] Implement `add_label` action: add specified label to the PR
- [ ] Implement `notify_team` action: send Slack/Teams notification to specified team channel
- [ ] Create `storage/audit_log.py` — SQLite table logging every policy evaluation: timestamp, PR, policy name, result (pass/fail), action taken
- [ ] Extend `DecisionsLog` schema or create separate `audit.db`

### Day 5: Testing & Documentation
- [ ] Test complex policy: "PRs touching `src/payments/**` by AI authors require 2 approvals from @payments-team"
- [ ] Test policy precedence: multiple policies matching same PR, most restrictive wins
- [ ] Test `conflicts_with_repo` condition for multi-repo policy enforcement
- [ ] Verify audit log captures all evaluations including passes
- [ ] Test graceful handling of malformed policies (skip with warning, don't crash)
- [ ] Add example policies to `.mergeguard.yml.example`

## Deliverables
- [ ] `core/policy.py` — Policy model, parser, and evaluation engine
- [ ] `storage/audit_log.py` — SQLite audit log for compliance
- [ ] Policy actions: block_merge, request_review, add_label, notify_team
- [ ] Extended `.mergeguard.yml` with `policies` section
- [ ] Example policies in config template

## Acceptance Criteria
- [ ] Policies defined declaratively in `.mergeguard.yml` with clear YAML syntax
- [ ] Conditions evaluated correctly against PR metadata, files, conflicts, and teams
- [ ] `block_merge` action prevents merge via commit status check
- [ ] `request_review` action creates review request on the PR
- [ ] Every policy evaluation logged in audit database with timestamp and outcome
- [ ] Malformed policies produce clear validation errors on config load
- [ ] Existing guardrails (`core/guardrails.py`) continue working alongside new policies

> **Extend:** `models.py` (Policy, PolicyResult models), `config.py` (parse policies section), `core/engine.py` (policy evaluation step), `core/guardrails.py` (coexistence with policies). **New:** `core/policy.py`, `storage/audit_log.py`.
