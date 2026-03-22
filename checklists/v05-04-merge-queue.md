# v0.5 — Feature 04: Merge Queue Integration

## Goals
- Use MergeGuard's conflict analysis to block conflicting PRs from merging in the wrong order
- Integrate with GitHub's native merge queue via required status checks
- Provide a path toward GitHub App installation for automated merge orchestration

## Daily Tasks

### Day 1-2: Status Check Integration
- [x] Add `post_commit_status()` method to `SCMClient` protocol in `integrations/protocol.py`
- [x] Implement GitHub commit status API in `integrations/github_client.py` using `POST /repos/{owner}/{repo}/statuses/{sha}`
- [x] Report `success` when no blocking conflicts, `failure` when CRITICAL conflicts exist, `pending` during analysis
- [x] Include conflict summary in status description (max 140 chars)
- [x] Add target_url pointing to the HTML dashboard or full comment
- [x] Implement equivalent for GitLab (pipeline status) and Bitbucket (build status)

### Day 3: Merge Order Enforcement
- [x] Extend `core/merge_order.py` `suggest_merge_order()` to output blocking recommendations
- [x] For each PR, determine if it's safe to merge now or if it should wait for specific other PRs
- [x] Add `merge_queue` section to `.mergeguard.yml`: `enabled`, `block_on_conflicts`, `block_severity` (default: critical)
- [x] Support priority override via PR labels: `merge-priority:high`, `merge-priority:low`
- [x] Read PR labels from `PRInfo.labels` (add field if missing) and factor into merge order

### Day 4: GitHub App Foundation
- [ ] Design GitHub App manifest for MergeGuard (permissions: pull_requests read/write, statuses write, checks write)
- [ ] Create `integrations/github_app.py` with JWT authentication for GitHub App
- [ ] Implement installation token refresh logic
- [ ] Wire GitHub App auth as an alternative to PAT in `cli.py` and `server/webhook.py`
- [ ] Document GitHub App creation and installation steps

### Day 5: Testing & Integration
- [x] Test status check flow: PR opened → analysis → status posted → merge queue respects status
- [x] Test priority override: high-priority PR jumps queue despite conflicts
- [ ] Test with GitHub's native merge queue (requires repo with merge queue enabled)
- [x] Verify status updates on re-analysis (pending → success/failure transitions)
- [x] Test graceful behavior when status API permissions are missing

## Deliverables
- [x] Commit status reporting on all three platforms
- [x] Merge order enforcement via required status checks
- [ ] GitHub App authentication module
- [x] Priority override via PR labels
- [x] Merge queue configuration in `.mergeguard.yml`

## Acceptance Criteria
- [x] CRITICAL conflicts cause `failure` status, blocking merge queue entry
- [x] WARNING-only conflicts allow merge with `success` status (configurable)
- [x] `merge-priority:high` label overrides conflict-based blocking
- [x] Status check updates automatically when conflicting PRs are merged/closed
- [ ] GitHub App auth works as alternative to personal access tokens
- [x] Works with GitHub's native merge queue and as standalone status checks

> **Extend:** `integrations/protocol.py` (new method), `integrations/github_client.py` (status API), `core/merge_order.py` (blocking recommendations), `models.py` (labels field, merge queue config), `cli.py` (merge queue options). **New:** `integrations/github_app.py`.
