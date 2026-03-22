<p align="center">
  <img src="assets/logo-with-text.svg" alt="MergeGuard" height="120">
</p>

<p align="center">
  <a href="https://pypi.org/project/py-mergeguard/"><img src="https://img.shields.io/pypi/v/py-mergeguard" alt="PyPI version"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

**Cross-PR intelligence for the agentic coding era.**

MergeGuard detects conflicts between open pull requests *before* they become merge headaches. It analyzes overlapping code changes across PRs using AST-level understanding — including cross-file symbol resolution — computes risk scores, and integrates seamlessly as a GitHub Action, CLI tool, or MCP server for AI agents.

![MergeGuard Demo](demo.gif)

## Why MergeGuard?

As AI coding agents (Cursor, Copilot, Devin, Claude Code) generate more PRs in parallel, the likelihood of *cross-PR conflicts* increases dramatically. Traditional CI only checks a single PR against the base branch — it can't see that two PRs are about to break each other.

MergeGuard fills this gap by:

- **Detecting hard conflicts** — two PRs modify the same function body
- **Catching interface conflicts** — one PR changes a function signature while another PR calls it (including cross-file via import analysis)
- **Identifying behavioral conflicts** — incompatible logic changes in the same module or across file boundaries
- **Flagging duplications** — two PRs implementing the same feature independently
- **Detecting regressions** — a PR re-introduces something recently removed
- **Enforcing guardrails** — configurable rules for import restrictions, complexity limits, forbidden patterns, and more
- **Posting inline annotations** — conflict warnings appear directly on the conflicting lines in PR diffs
- **Real-time webhook server** — instant conflict detection on PR open/update via GitHub, GitLab, and Bitbucket webhooks
- **CODEOWNERS-aware routing** — conflict notifications routed to the specific code owners, with per-team Slack channels
- **Stacked PR support** — detects PR stacks (branch chains, labels, Graphite), demotes expected intra-stack conflicts, and enforces stack-aware merge ordering
- **Merge queue integration** — commit status checks that block conflicting PRs from merging, with priority override via labels and GitHub merge group support
- **Blast radius visualization** — interactive D3.js force-directed graph showing PR conflict topology with transitive blast radius computation (`mergeguard blast-radius`)
- **Policy engine** — declarative conditions-and-actions system: block merges when AI-authored PRs have critical conflicts, auto-label high-risk PRs, require additional reviewers for infrastructure changes, notify Slack channels based on affected teams
- **Computing risk scores** — composite scoring with configurable weights based on conflict severity, blast radius, code churn, and AI attribution

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
      - uses: Vansh2795/mergeguard@v0.1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### As a CLI

```bash
# Install from PyPI
pip install py-mergeguard

# Analyze a specific PR
mergeguard analyze --repo owner/repo --pr 42 --token $GITHUB_TOKEN

# Analyze without inline annotations (summary comment only)
mergeguard analyze --repo owner/repo --pr 42 --token $GITHUB_TOKEN --no-inline

# Output as JSON, SARIF, or HTML
mergeguard analyze --repo owner/repo --pr 42 --token $GITHUB_TOKEN --format json
mergeguard analyze --repo owner/repo --pr 42 --token $GITHUB_TOKEN --format html

# Show collision map of all open PRs
mergeguard map --repo owner/repo --token $GITHUB_TOKEN

# Risk dashboard (terminal or HTML)
mergeguard dashboard --repo owner/repo --token $GITHUB_TOKEN
mergeguard dashboard --repo owner/repo --token $GITHUB_TOKEN --format html

# Suggest optimal merge order
mergeguard suggest-order --repo owner/repo --token $GITHUB_TOKEN

# Blast radius visualization (interactive HTML graph)
mergeguard blast-radius --repo owner/repo --token $GITHUB_TOKEN
mergeguard blast-radius --repo owner/repo --token $GITHUB_TOKEN --format terminal
mergeguard blast-radius --repo owner/repo --token $GITHUB_TOKEN -o blast-radius.html

# Watch for changes and re-analyze automatically
mergeguard watch --repo owner/repo --token $GITHUB_TOKEN

# Interactive setup wizard
mergeguard init

# Evaluate policy rules against a PR (dry-run by default)
mergeguard policy-check --repo owner/repo --pr 42 --token $GITHUB_TOKEN
mergeguard policy-check --repo owner/repo --pr 42 --token $GITHUB_TOKEN --execute

# Start webhook server for real-time analysis
mergeguard serve --port 8000
```

## How It Works

1. **Fetch** — Retrieves all open PRs and their diffs from GitHub, GitLab, or Bitbucket
2. **Parse** — Uses Tree-sitter to build AST-level understanding of changed code
3. **Detect** — Compares every pair of open PRs for overlapping changes, including cross-file conflicts via import/symbol analysis
4. **Classify** — Categorizes conflicts (hard, interface, behavioral, duplication, transitive, regression, guardrail)
5. **Score** — Computes a composite risk score (0-100) with configurable weights
6. **Report** — Posts actionable comments on PRs with inline annotations on conflicting lines, renders terminal output with diff previews, generates HTML reports, or sends Slack/Teams notifications

## Platforms

| Platform | Status |
|----------|--------|
| GitHub (cloud + Enterprise Server) | Supported |
| GitLab (cloud + self-hosted) | Supported |
| Bitbucket Cloud | Supported |

## Configuration

Create a `.mergeguard.yml` in your repository root (or run `mergeguard init` for guided setup):

```yaml
risk_threshold: 50        # Only comment if risk score > 50
check_regressions: true   # Detect regressions against recent merges
max_open_prs: 30          # Performance limit
llm_enabled: false        # Optional AI-powered semantic analysis
max_transitive_per_pair: 5  # Max transitive conflicts per PR pair
ignored_paths:
  - "*.lock"
  - "package-lock.json"

# Custom risk weights (must sum to ~1.0)
# risk_weights:
#   conflict_severity: 0.40
#   blast_radius: 0.20
#   pattern_deviation: 0.15
#   churn_risk: 0.15
#   ai_attribution: 0.10
```

### Policy Engine

Define automated merge policies that evaluate conflict analysis results:

```yaml
policy:
  enabled: true
  policies:
    - name: block-critical-ai-prs
      conditions:
        - field: ai_authored
          operator: eq
          value: true
        - field: has_severity
          operator: contains
          value: critical
      actions:
        - action: block_merge
          message: "AI-authored PR has critical conflicts"
        - action: require_reviewers
          reviewers: ["@platform-team"]

    - name: label-high-risk
      conditions:
        - field: risk_score
          operator: gte
          value: 80
      actions:
        - action: add_labels
          labels: ["high-risk"]
        - action: notify_slack
          webhook_url: "https://hooks.slack.com/..."
```

See [Configuration Guide](docs/configuration.md) for all options including guardrail rules, notifications, and performance tuning.

## Documentation

- [Getting Started](docs/getting-started.md)
- [CI Setup](docs/ci-setup.md) — GitHub Actions, GitLab CI, and advanced integration
- [How It Works](docs/how-it-works.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Contributing](docs/contributing.md)
- [FAQ](docs/faq.md)
- [Changelog](CHANGELOG.md)
- [Roadmap](ROADMAP.md)

## Development

```bash
# Clone and setup
git clone https://github.com/Vansh2795/mergeguard.git
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
