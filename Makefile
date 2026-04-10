.PHONY: install dev test lint format type-check all help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install package
	uv sync

dev:  ## Install with dev dependencies
	uv sync --dev

test:  ## Run tests with coverage
	uv run pytest --cov=mergeguard --cov-report=term-missing

lint:  ## Run linter
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format:  ## Auto-format code
	uv run ruff format src/ tests/

type-check:  ## Run type checker
	uv run mypy src/

all: lint type-check test  ## Run all checks
