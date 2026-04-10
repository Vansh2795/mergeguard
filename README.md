<p align="center">
  <img src="assets/logo-with-text.svg" alt="MergeGuard" height="120">
</p>

<p align="center">
  <a href="https://pypi.org/project/py-mergeguard/"><img src="https://img.shields.io/pypi/v/py-mergeguard" alt="PyPI version"></a>
  <a href="https://github.com/Vansh2795/mergeguard/actions/workflows/ci.yml"><img src="https://github.com/Vansh2795/mergeguard/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

# MergeGuard

**Detect cross-PR conflicts before they reach your merge queue.**

MergeGuard analyzes open pull requests and finds conflicts between them — hard overlaps, interface breaks, behavioral incompatibilities, duplications, transitive dependencies, and regressions — while you're still developing, not at merge time.

## The Problem

Traditional CI checks a single PR against the base branch. It can't see that two PRs are about to break each other. Merge queues (Mergify, Trunk, Aviator) catch this at merge time — but by then you've already done the work.

MergeGuard catches it during development.

## Quick Start

```bash
pip install py-mergeguard

cd your-repo
export GITHUB_TOKEN=ghp_...
mergeguard analyze --pr 42
```

That's it. Auto-detects platform and repo from your git remote.

## What It Detects

| Type | Example |
|------|---------|
| **Hard conflict** | Two PRs modify the same function body |
| **Interface conflict** | PR A changes a function signature, PR B calls it (cross-file) |
| **Behavioral conflict** | Incompatible logic changes in the same module |
| **Duplication** | Two PRs independently implement the same feature |
| **Transitive** | PR A changes a module that PR B's files depend on |
| **Regression** | A PR re-introduces something recently removed |

## GitHub Action

```yaml
name: MergeGuard
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Vansh2795/mergeguard@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## How It Compares

| | MergeGuard | Merge Queues (Mergify, Trunk) | AI Review (CodeRabbit, Qodo) |
|---|---|---|---|
| Detects cross-PR conflicts | During development | At merge time | No |
| Requires workflow change | No | Yes (adopt queue) | No |
| Open source | MIT | Commercial | Commercial |
| Multi-platform | GitHub + GitLab + Bitbucket | GitHub only (mostly) | GitHub (mostly) |

## Platforms

| Platform | Status |
|----------|--------|
| GitHub (Cloud + Enterprise Server) | Supported |
| GitLab (Cloud + self-hosted) | Supported |
| Bitbucket Cloud | Supported |

## CLI Commands

```bash
mergeguard analyze --pr 42          # Analyze a PR for cross-PR conflicts
mergeguard map                      # Collision map of all open PRs
mergeguard suggest-order            # Optimal merge sequence
mergeguard watch                    # Continuous monitoring
mergeguard serve                    # Webhook server for real-time detection
mergeguard init                     # Interactive setup wizard
```

## Configuration

```yaml
# .mergeguard.yml
risk_threshold: 50
max_open_prs: 30
ignored_paths:
  - "*.lock"
  - "package-lock.json"
```

See [Configuration Guide](docs/configuration.md) for all options.

## Benchmarks

Tested against real open-source repos. Transitive accuracy improvements reduced false positives by 59-82% on FastAPI. See [Benchmark Results](benchmarks/BENCHMARKS.md).

## Documentation

- [Getting Started](docs/getting-started.md)
- [How It Works](docs/how-it-works.md)
- [CI Setup](docs/ci-setup.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Benchmark Results](benchmarks/BENCHMARKS.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Also Included

MergeGuard ships with additional features for enterprise workflows:

- **Policy engine** — declarative conditions-and-actions for merge automation
- **DORA metrics** — conflict resolution time tracking
- **Blast radius visualization** — interactive D3.js dependency graph
- **CODEOWNERS routing** — team-aware Slack/Teams notifications
- **Merge queue integration** — commit status checks with priority labels
- **Stacked PR support** — Graphite, branch chains, label-based detection
- **MCP server** — AI agent integration (`check_conflicts`, `get_risk_score`, `suggest_merge_order`)

See [docs/](docs/) for details on each feature.

## Development

```bash
git clone https://github.com/Vansh2795/mergeguard.git
cd mergeguard
uv sync --dev
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

## License

MIT — see [LICENSE](LICENSE).
