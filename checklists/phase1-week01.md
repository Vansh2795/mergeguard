# Phase 1 — Week 1: Project Scaffold + GitHub Integration

## Goals
- Working project that can fetch all open PRs and their changed files from any GitHub repo
- CI pipeline running on every push

## Daily Tasks

### Day 1-2: Project Initialization
- [ ] Initialize repo with uv: `uv init mergeguard --lib --python 3.12`
- [ ] Set up src layout with all directories
- [ ] Create pyproject.toml with all dependencies and tool configs
- [ ] Set up CI (GitHub Actions for ruff, mypy, pytest on every push)
- [ ] Write README skeleton with project vision
- [ ] Create Pydantic data models (models.py)
- [ ] Implement config.py — loads .mergeguard.yml with sensible defaults

### Day 3-4: GitHub Client
- [ ] Implement `GitHubClient` class with PyGithub
- [ ] `get_open_prs()` — fetch all open PRs with metadata
- [ ] `get_pr_files()` — fetch changed files per PR
- [ ] `get_pr_diff()` — fetch full unified diff
- [ ] `get_file_content()` — fetch file at specific branch/commit
- [ ] `post_pr_comment()` — post/update MergeGuard comments
- [ ] `set_commit_status()` — set pass/warn/fail status

### Day 5: Tests
- [ ] Create mock API responses in tests/fixtures/api_responses/
- [ ] Test get_open_prs, get_pr_files, get_pr_diff with mocked responses
- [ ] Test error handling (rate limits, 404s, auth failures)

## Deliverables
- [ ] Working GitHub client that can fetch real PR data
- [ ] CI pipeline with lint + type check + test
- [ ] All Pydantic models defined and validated
- [ ] Config loader with sensible defaults

## Acceptance Criteria
- [ ] `mergeguard` package can be imported without errors
- [ ] `GitHubClient` successfully fetches PRs from a test repository
- [ ] All tests pass: `uv run pytest`
- [ ] Lint clean: `uv run ruff check src/`
- [ ] Type check clean: `uv run mypy src/`
