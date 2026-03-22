# v0.5 — Feature 05: Stacked PR Awareness

## Goals
- Detect PR dependency chains (stacked PRs) and adjust conflict analysis accordingly
- Suppress expected intra-stack conflicts while escalating cross-stack conflicts
- Support Graphite metadata, branch chain detection, and manual stack annotations

## Daily Tasks

### Day 1-2: Stack Detection Engine
- [ ] Create `analysis/stacked_prs.py` module
- [ ] Implement branch chain detection: PR B's base branch is PR A's head branch
- [ ] Implement Graphite metadata detection: read `graphite` labels or `Graphite-base:` trailer in PR body
- [ ] Implement manual annotation: detect `stack:group-name` PR labels
- [ ] Build `StackGroup` model: list of PRs in dependency order with group identifier
- [ ] Add `detect_stacks(prs: list[PRInfo]) -> list[StackGroup]` function
- [ ] Handle partial stacks (middle PR merged, stack splits into two groups)

### Day 3: Conflict Adjustment
- [ ] Wire stack detection into `core/engine.py` before conflict classification
- [ ] For intra-stack conflicts (both PRs in same stack): demote severity to INFO
- [ ] For cross-stack conflicts (stacked PR vs unrelated PR): keep original severity or escalate
- [ ] Add `stack_group: str | None` field to `ConflictReport` model
- [ ] Add `is_intra_stack: bool` field to `Conflict` model
- [ ] Preserve original severity in `Conflict.original_severity` for transparency

### Day 4: Output & Visualization
- [ ] Update `output/github_comment.py` to show stack context: "Part of stack: #10 → #11 → #12"
- [ ] Update `output/terminal.py` to group stacked PRs visually in the conflict matrix
- [ ] Update `output/dashboard_html.py` to render stack chains as a connected subgraph
- [ ] Add stack info to `output/json_report.py` for API consumers
- [ ] Show demoted intra-stack conflicts in a collapsed section (not hidden entirely)

### Day 5: Configuration & Testing
- [ ] Add `stacked_prs` section to `.mergeguard.yml`: `enabled`, `detection` (`auto` | `graphite` | `branch_chain` | `labels`)
- [ ] Test with real Graphite-managed stacked PRs
- [ ] Test branch chain detection across various naming conventions
- [ ] Test edge case: circular dependencies (PR A based on PR B based on PR A) — should warn, not crash
- [ ] Test stack splitting when middle PR is merged
- [ ] Verify intra-stack demotions don't hide genuinely dangerous conflicts

## Deliverables
- [ ] `analysis/stacked_prs.py` — stack detection with multiple strategies
- [ ] Extended `Conflict` and `ConflictReport` models with stack-aware fields
- [ ] Adjusted conflict severity for intra-stack vs cross-stack conflicts
- [ ] Stack visualization in terminal, comment, and dashboard outputs

## Acceptance Criteria
- [ ] Stacked PRs detected automatically via branch chain or Graphite metadata
- [ ] Intra-stack conflicts demoted to INFO severity with clear labeling
- [ ] Cross-stack conflicts retain original severity
- [ ] PR comments show stack context (position in chain, link to other stack PRs)
- [ ] Dashboard renders stack chains as connected subgraphs
- [ ] Graceful handling of malformed stacks (circular deps, orphaned PRs)

> **Extend:** `models.py` (StackGroup model, stack fields on Conflict/ConflictReport), `core/engine.py` (stack detection step), `output/github_comment.py` (stack context), `output/terminal.py` (grouped display), `output/dashboard_html.py` (stack subgraph), `config.py` (stacked_prs config). **New:** `analysis/stacked_prs.py`.
