# v0.5 — Feature 01: Inline PR Annotations (Line-Level Comments)

## Goals
- Post conflict warnings as line-level review comments on the exact conflicting code, not just a summary comment
- Support GitHub, GitLab, and Bitbucket review APIs
- Keep existing summary comment as an overview with links to inline annotations

## Daily Tasks

### Day 1-2: GitHub Review API Integration
- [x] Add `post_pr_review()` method to `SCMClient` protocol in `integrations/protocol.py`
- [x] Implement GitHub review posting in `integrations/github_client.py` using `POST /repos/{owner}/{repo}/pulls/{pr}/reviews`
- [x] Group all annotations into a single review (avoid notification spam)
- [x] Map `ConflictSeverity` to GitHub review event: CRITICAL → REQUEST_CHANGES, WARNING → COMMENT, INFO → COMMENT
- [x] Handle GitHub API limits (max 60 comments per review)

### Day 3: Annotation Formatter
- [x] Create `output/inline_annotations.py` formatter
- [x] Convert each `Conflict` to a review comment with `path`, `line`, `body`
- [x] Resolve line numbers from `Conflict.files` and `Conflict.symbols` to diff positions
- [x] Include conflict type, severity, recommendation, and link to conflicting PR in comment body
- [x] Use GitHub suggestion blocks for simple fix recommendations from `core/fix_templates.py`

### Day 4: GitLab & Bitbucket Support
- [x] Implement GitLab inline comments via `POST /projects/:id/merge_requests/:mr/discussions` with position object
- [x] Implement Bitbucket inline comments via `POST /repositories/{workspace}/{repo}/pullrequests/{id}/comments` with inline object
- [x] Abstract diff position calculation (GitHub uses diff hunk position, GitLab uses new/old line, Bitbucket uses line/path)

### Day 5: Integration & Summary Links
- [x] Wire inline annotations into `core/engine.py` analysis pipeline
- [x] Update `output/github_comment.py` summary to include anchored links to each inline annotation
- [x] Add `inline_annotations` config option to `.mergeguard.yml` (default: true)
- [x] Add `--no-inline` CLI flag to `cli.py` for summary-only mode
- [x] Test with real PRs on all three platforms
- [x] Update existing annotation on re-analysis (resolve stale comments)

## Deliverables
- [x] `output/inline_annotations.py` — formatter converting Conflicts to platform-specific review comments
- [x] Extended `SCMClient` protocol with `post_pr_review()` method
- [x] GitHub, GitLab, Bitbucket review posting implementations
- [x] Updated summary comment with links to inline annotations

## Acceptance Criteria
- [x] Conflicts appear as line-level comments on the exact conflicting lines in PR diffs
- [x] All annotations grouped into a single review per analysis run (no notification spam)
- [x] Summary comment links to each inline annotation
- [x] Works on GitHub Cloud, GitHub Enterprise Server, GitLab, and Bitbucket Cloud
- [x] Stale annotations from previous runs are resolved/dismissed on re-analysis
- [x] Graceful fallback to summary-only when review API is unavailable

> **Extend:** `integrations/protocol.py` (new method), `integrations/github_client.py` (review API), `output/github_comment.py` (summary links), `core/engine.py` (wire formatting), `config.py` / `models.py` (new config option).
