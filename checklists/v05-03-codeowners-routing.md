# v0.5 — Feature 03: CODEOWNERS & Team-Aware Routing

## Goals
- Parse CODEOWNERS files to map files to owning teams/individuals
- Route conflict notifications to the specific owners of affected code
- Tag relevant code owners in PR comments and Slack/Teams messages

## Daily Tasks

### Day 1-2: CODEOWNERS Parser
- [x] Create `analysis/codeowners.py` module
- [x] Parse GitHub `.github/CODEOWNERS` format (glob patterns, @user and @org/team handles)
- [x] Parse GitLab `CODEOWNERS` format (sections with `[Section]` headers)
- [x] Support multiple CODEOWNERS file locations: `.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS`
- [x] Implement `resolve_owners(file_path: str) -> list[str]` — match file against patterns (last match wins for GitHub)
- [x] Cache parsed CODEOWNERS per repo in `storage/cache.py`

### Day 3: Conflict-to-Owner Mapping
- [x] For each `Conflict`, resolve owners of all involved files via CODEOWNERS
- [x] Add `owners: list[str]` field to `Conflict` model in `models.py`
- [x] Add `affected_teams: list[str]` field to `ConflictReport` model
- [x] Wire owner resolution into `core/engine.py` after conflict classification
- [x] Group conflicts by team for per-team summaries

### Day 4: Team-Aware Notifications
- [x] Update `output/github_comment.py` to @mention code owners next to their conflicts
- [x] Update `output/notifications.py` Slack integration to mention owning team/channel
- [x] Update `output/notifications.py` Teams integration with team-specific adaptive cards
- [x] Add per-team notification routing config: map CODEOWNERS teams to Slack channels
- [x] Add `codeowners` section to `.mergeguard.yml`: `enabled`, `path` (auto-detect by default), `team_channels` mapping

### Day 5: Testing & Edge Cases
- [x] Test with real-world CODEOWNERS files (nested globs, wildcards, team handles)
- [x] Handle missing CODEOWNERS gracefully (skip owner resolution, log warning)
- [x] Handle files with no matching CODEOWNERS entry (assign to default/global owners)
- [x] Test cross-team conflicts: PR A (team-frontend) conflicts with PR B (team-backend)
- [x] Verify @mentions render correctly on GitHub/GitLab

## Deliverables
- [x] `analysis/codeowners.py` — CODEOWNERS parser with `resolve_owners()` API
- [x] Extended `Conflict` and `ConflictReport` models with owner fields
- [x] Team-aware PR comments with @mentions
- [x] Team-routed Slack/Teams notifications

## Acceptance Criteria
- [x] CODEOWNERS files parsed correctly for GitHub and GitLab formats
- [x] PR comments tag the specific code owners for each conflict
- [x] Slack notifications route to the correct team channel based on CODEOWNERS mapping
- [x] Conflicts between different teams are highlighted as cross-team conflicts
- [x] Graceful degradation when CODEOWNERS file is missing or malformed
- [x] Auto-detects CODEOWNERS location without explicit config

> **Extend:** `models.py` (owner fields on Conflict/ConflictReport), `core/engine.py` (owner resolution step), `output/github_comment.py` (@mentions), `output/notifications.py` (team routing), `config.py` (codeowners config). **New:** `analysis/codeowners.py`.
