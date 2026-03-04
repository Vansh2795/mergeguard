# Phase 1 — Week 1: Project Scaffold + GitHub Integration

## Goals
- Working project that can fetch all open PRs and their changed files from any GitHub repo
- CI pipeline running on every push

## Daily Tasks

### Day 1-2: Project Initialization
- [x] Initialize repo with uv: `uv init mergeguard --lib --python 3.12`
- [x] Set up src layout with all directories
- [x] Create pyproject.toml with all dependencies and tool configs
- [x] Set up CI (GitHub Actions for ruff, mypy, pytest on every push)
- [x] Write README skeleton with project vision
- [x] Create Pydantic data models (models.py)
- [x] Implement config.py — loads .mergeguard.yml with sensible defaults

### Day 3-4: GitHub Client
- [x] Implement `GitHubClient` class with PyGithub
- [x] `get_open_prs()` — fetch all open PRs with metadata
- [x] `get_pr_files()` — fetch changed files per PR
- [x] `get_pr_diff()` — fetch full unified diff
- [x] `get_file_content()` — fetch file at specific branch/commit
- [x] `post_pr_comment()` — post/update MergeGuard comments
- [x] `set_commit_status()` — set pass/warn/fail status

### Day 5: Tests
- [x] Create mock API responses in tests/fixtures/api_responses/
- [x] Test get_open_prs, get_pr_files, get_pr_diff with mocked responses
- [x] Test error handling (rate limits, 404s, auth failures)

## Deliverables
- [x] Working GitHub client that can fetch real PR data
- [x] CI pipeline with lint + type check + test
- [x] All Pydantic models defined and validated
- [x] Config loader with sensible defaults

## Acceptance Criteria
- [x] `mergeguard` package can be imported without errors
- [x] `GitHubClient` successfully fetches PRs from a test repository
- [x] All tests pass: `uv run pytest`
- [x] Lint clean: `uv run ruff check src/`
- [x] Type check clean: `uv run mypy src/`
