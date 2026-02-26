# MergeGuard

**Cross-PR intelligence for the agentic coding era.**

MergeGuard detects conflicts between open pull requests *before* they become merge headaches. It analyzes overlapping code changes across PRs using AST-level understanding, computes risk scores, and integrates seamlessly as a GitHub Action or CLI tool.

## Why MergeGuard?

As AI coding agents (Cursor, Copilot, Devin, Claude Code) generate more PRs in parallel, the likelihood of *cross-PR conflicts* increases dramatically. Traditional CI only checks a single PR against the base branch — it can't see that two PRs are about to break each other.

MergeGuard fills this gap by:

- **Detecting hard conflicts** — two PRs modify the same function body
- **Catching interface conflicts** — one PR changes a function signature while another PR calls it
- **Identifying behavioral conflicts** — incompatible logic changes in the same module
- **Flagging duplications** — two PRs implementing the same feature independently
- **Detecting regressions** — a PR re-introduces something recently removed
- **Computing risk scores** — composite scoring based on conflict severity, blast radius, code churn, and AI attribution

## Quick Start

### As a GitHub Action

```yaml
# .github/workflows/mergeguard.yml
name: MergeGuard
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: mergeguard/mergeguard@v0.1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### As a CLI

```bash
# Install
pip install mergeguard

# Analyze a specific PR
mergeguard analyze --repo owner/repo --pr 42 --token $GITHUB_TOKEN

# Show collision map of all open PRs
mergeguard map --repo owner/repo --token $GITHUB_TOKEN

# Risk dashboard for all open PRs
mergeguard dashboard --repo owner/repo --token $GITHUB_TOKEN
```

## How It Works

1. **Fetch** — Retrieves all open PRs and their diffs from GitHub
2. **Parse** — Uses Tree-sitter to build AST-level understanding of changed code
3. **Detect** — Compares every pair of open PRs for overlapping changes
4. **Classify** — Categorizes conflicts (hard, interface, behavioral, duplication, regression)
5. **Score** — Computes a composite risk score (0-100) for each PR
6. **Report** — Posts actionable comments on PRs or displays results in the terminal

## Configuration

Create a `.mergeguard.yml` in your repository root:

```yaml
risk_threshold: 50        # Only comment if risk score > 50
check_regressions: true   # Detect regressions against recent merges
max_open_prs: 30          # Performance limit
llm_enabled: false        # Optional AI-powered semantic analysis
ignored_paths:
  - "*.lock"
  - "package-lock.json"
```

See [Configuration Guide](docs/configuration.md) for all options.

## Documentation

- [Getting Started](docs/getting-started.md)
- [How It Works](docs/how-it-works.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Contributing](docs/contributing.md)
- [FAQ](docs/faq.md)

## Development

```bash
# Clone and setup
git clone https://github.com/mergeguard/mergeguard.git
cd mergeguard
uv sync --dev

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
uv run mypy src/
```

## License

MIT — see [LICENSE](LICENSE).
