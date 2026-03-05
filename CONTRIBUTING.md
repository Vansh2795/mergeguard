# Contributing to MergeGuard

Thanks for your interest in contributing! MergeGuard is an open-source project and we welcome contributions of all kinds — bug fixes, new features, documentation, and ideas.

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Development Setup

```bash
git clone https://github.com/Vansh2795/mergeguard.git
cd mergeguard

# Install dependencies (including dev dependencies)
uv sync --dev

# Verify everything works
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

### Running Tests

```bash
uv run pytest                                    # All tests
uv run pytest -v                                 # Verbose output
uv run pytest --cov=mergeguard --cov-report=html # With coverage
uv run pytest tests/unit/test_gitlab_client.py   # Specific file
uv run pytest -k "test_parse"                    # Pattern match
```

## Project Structure

```
src/mergeguard/
├── models.py              # Pydantic data models (PRInfo, Conflict, etc.)
├── cli.py                 # Click CLI commands (analyze, map, dashboard)
├── config.py              # YAML config loader
├── constants.py           # Shared constants
├── analysis/              # Diff parsing, AST analysis, symbol extraction
├── core/                  # Engine, conflict detection, risk scoring
│   ├── engine.py          # Main orchestrator
│   ├── conflict.py        # Conflict classification
│   └── risk_scorer.py     # Risk score computation
├── integrations/          # Platform clients
│   ├── protocol.py        # SCMClient protocol (interface for all platforms)
│   ├── github_client.py   # GitHub REST API
│   ├── gitlab_client.py   # GitLab REST API v4
│   └── git_local.py       # Local git operations
└── output/                # Report formatters (markdown, JSON, terminal)
```

## Where to Contribute

### Good First Issues

Look for issues labeled [`good first issue`](https://github.com/Vansh2795/mergeguard/labels/good%20first%20issue) — these are scoped, well-documented, and don't require deep familiarity with the codebase.

### Areas We Need Help With

- **New platform integrations** — Bitbucket, Azure DevOps, Gitea ([#2](https://github.com/Vansh2795/mergeguard/issues/2))
- **Output formats** — JUnit XML, HTML reports
- **CI/CD examples** — GitHub Actions, GitLab CI, Jenkins ([#4](https://github.com/Vansh2795/mergeguard/issues/4))
- **Documentation** — tutorials, blog posts, demo recordings ([#6](https://github.com/Vansh2795/mergeguard/issues/6))
- **Bug reports and fixes** — always welcome

### Adding a New Platform Integration

MergeGuard uses a `SCMClient` protocol (`src/mergeguard/integrations/protocol.py`). To add a new platform:

1. Create `src/mergeguard/integrations/<platform>_client.py` implementing `SCMClient`
2. Use `httpx` for HTTP requests (already a dependency)
3. Add detection to `git_local.py:detect_platform()`
4. Wire it into `cli.py:_create_client()`
5. Add tests using `respx` (see `tests/unit/test_gitlab_client.py` for the pattern)

## Code Style

We use `ruff` for linting and formatting:

```bash
uv run ruff check src/ tests/       # Lint
uv run ruff check --fix src/ tests/  # Auto-fix
uv run ruff format src/ tests/       # Format
uv run mypy src/                     # Type check
```

### Conventions

- `from __future__ import annotations` in every module
- Pydantic V2 for data models (`BaseModel`, `Field()`, `model_dump()`)
- Click for CLI commands
- `httpx` for HTTP (not `requests`)
- `respx` for mocking HTTP in tests
- Lazy-import optional dependencies (anthropic, mcp)

## Pull Request Guidelines

1. **Keep PRs focused** — one feature or fix per PR
2. **Add tests** — all new code should have corresponding tests
3. **Run CI locally** before pushing:
   ```bash
   uv run pytest && uv run ruff check src/ tests/ && uv run mypy src/
   ```
4. **Update docs** if you change behavior
5. **Follow existing patterns** — look at similar code in the repo before writing new code
6. **Write clear commit messages** — explain *why*, not just *what*

## Reporting Issues

File issues at https://github.com/Vansh2795/mergeguard/issues with:

- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
- MergeGuard version (`mergeguard --version`)

## Questions?

Open a [GitHub Discussion](https://github.com/Vansh2795/mergeguard/discussions) or comment on the relevant issue. We're happy to help you get started.
