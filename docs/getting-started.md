<p align="center">
  <img src="../assets/logo.svg" alt="MergeGuard" height="64">
</p>

# Getting Started with MergeGuard

Get MergeGuard running in 5 minutes.

## Prerequisites

- Python 3.12+
- A GitHub repository with open pull requests
- A GitHub personal access token (or `GITHUB_TOKEN` in CI)

## Installation

### Via pip

```bash
pip install py-mergeguard
```

### Via uv (recommended)

```bash
uv add py-mergeguard
```

### From source

```bash
git clone https://github.com/Vansh2795/mergeguard.git
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
      - uses: Vansh2795/mergeguard@v0.1
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

# Output as JSON, SARIF, or HTML
mergeguard analyze --repo owner/repo --pr 42 --format json
mergeguard analyze --repo owner/repo --pr 42 --format html

# Show the collision map of all open PRs
mergeguard map --repo owner/repo

# Risk dashboard (terminal or HTML with charts)
mergeguard dashboard --repo owner/repo
mergeguard dashboard --repo owner/repo --format html

# Suggest optimal merge order
mergeguard suggest-order --repo owner/repo

# Watch for PR changes and re-analyze
mergeguard watch --repo owner/repo

# Interactive setup wizard
mergeguard init
```

### Other Platforms

```bash
# GitLab
mergeguard analyze --platform gitlab --repo group/project --pr 42 --token $GITLAB_TOKEN

# Bitbucket Cloud
mergeguard analyze --platform bitbucket --repo workspace/repo --pr 42 --token $BITBUCKET_APP_PASSWORD

# GitHub Enterprise Server
mergeguard --github-url https://github.example.com analyze --repo owner/repo --pr 42
```

## Configuration

Create a `.mergeguard.yml` file in your repository root (or run `mergeguard init` for guided setup):

```yaml
risk_threshold: 50
check_regressions: true
max_open_prs: 30
max_transitive_per_pair: 5
ignored_paths:
  - "*.lock"
  - "package-lock.json"
```

See the [Configuration Guide](configuration.md) for all options including guardrail rules, risk weights, and performance tuning.

## What's Next?

- Set up [CI Integration](ci-setup.md) for GitHub Actions or GitLab CI
- Read [How It Works](how-it-works.md) to understand the analysis pipeline
- See [Configuration](configuration.md) for all available options
- Check [Architecture](architecture.md) for the technical deep dive
- Want to contribute? See [Contributing](contributing.md)
