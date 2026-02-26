# Getting Started with MergeGuard

Get MergeGuard running in 5 minutes.

## Prerequisites

- Python 3.12+
- A GitHub repository with open pull requests
- A GitHub personal access token (or `GITHUB_TOKEN` in CI)

## Installation

### Via pip

```bash
pip install mergeguard
```

### Via uv (recommended)

```bash
uv add mergeguard
```

### From source

```bash
git clone https://github.com/mergeguard/mergeguard.git
cd mergeguard
uv sync
```

## Quick Start: GitHub Action

The fastest way to use MergeGuard is as a GitHub Action. Add this workflow to your repository:

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

That's it! MergeGuard will now automatically analyze every PR for cross-PR conflicts and post a comment with the results.

## Quick Start: CLI

For local development, use the CLI:

```bash
# Set your GitHub token
export GITHUB_TOKEN=ghp_your_token_here

# Analyze a specific PR
mergeguard analyze --repo owner/repo --pr 42

# Show the collision map of all open PRs
mergeguard map --repo owner/repo

# Risk dashboard for all open PRs
mergeguard dashboard --repo owner/repo
```

## Configuration

Create a `.mergeguard.yml` file in your repository root to customize behavior:

```yaml
risk_threshold: 50
check_regressions: true
max_open_prs: 30
ignored_paths:
  - "*.lock"
  - "package-lock.json"
```

See the [Configuration Guide](configuration.md) for all options.

## What's Next?

- Read [How It Works](how-it-works.md) to understand the analysis pipeline
- See [Configuration](configuration.md) for all available options
- Check [Architecture](architecture.md) for the technical deep dive
- Want to contribute? See [Contributing](contributing.md)
