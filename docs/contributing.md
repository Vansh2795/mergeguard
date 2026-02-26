# Contributing to MergeGuard

We welcome contributions! Here's how to get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/mergeguard/mergeguard.git
cd mergeguard

# Install uv (if you haven't already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (including dev dependencies)
uv sync --dev

# Verify everything works
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

## Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=mergeguard --cov-report=html

# Run specific test file
uv run pytest tests/unit/test_diff_parser.py

# Run tests matching a pattern
uv run pytest -k "test_parse"
```

## Code Style

We use `ruff` for both linting and formatting:

```bash
# Check for lint errors
uv run ruff check src/ tests/

# Auto-fix lint errors
uv run ruff check --fix src/ tests/

# Check formatting
uv run ruff format --check src/ tests/

# Auto-format
uv run ruff format src/ tests/
```

## Type Checking

```bash
uv run mypy src/
```

## Pull Request Guidelines

1. **Keep PRs focused**: One feature or fix per PR
2. **Add tests**: All new code should have corresponding tests
3. **Update docs**: If you change behavior, update the docs
4. **Follow existing patterns**: Use Pydantic models for data, Click for CLI
5. **Run CI locally**: `uv run pytest && uv run ruff check src/ tests/ && uv run mypy src/`

## Architecture Notes

- All data models live in `src/mergeguard/models.py`
- Use `from __future__ import annotations` in every module
- Lazy-import optional dependencies (anthropic, mcp)
- Use Pydantic V2 patterns: `BaseModel`, `Field()`, `model_dump()`

## Reporting Issues

Please report issues at https://github.com/mergeguard/mergeguard/issues with:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Python version and OS
