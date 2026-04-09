# CI Setup Guide

Integrate MergeGuard into your CI pipeline so every pull request is automatically analyzed for cross-PR conflicts.

## GitHub Actions (Docker Action) — Recommended

The Docker-based action bundles all dependencies and runs out of the box:

```yaml
# .github/workflows/mergeguard.yml
name: MergeGuard
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Vansh2795/mergeguard@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Action inputs

| Input | Description | Default |
|-------|-------------|---------|
| `github-token` | GitHub token with PR read/write access | *required* |
| `anthropic-api-key` | Anthropic API key for LLM-powered analysis | — |
| `risk-threshold` | Minimum risk score to post a comment | `0` |
| `fail-on-risk` | Fail the check when risk exceeds threshold | `false` |
| `max-open-prs` | Maximum open PRs to analyze (safety cap) | `200` |
| `max-pr-age` | Only scan PRs updated within this many days | `30` |
| `config-path` | Path to config file | `.mergeguard.yml` |
| `github-url` | GitHub Enterprise Server URL | — |
| `merge-queue` | Enable merge queue integration (posts commit status) | `false` |
| `block-severity` | Minimum severity to block merge (critical/warning/info) | `critical` |

### Action outputs

| Output | Description |
|--------|-------------|
| `risk-score` | Numeric risk score (0–100) |
| `conflict-count` | Number of detected conflicts |
| `report-json` | Full analysis report as JSON |

## GitHub Actions (pip install)

A lighter alternative that doesn't require Docker:

```yaml
name: MergeGuard Analysis
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install py-mergeguard
      - name: Run MergeGuard
        run: mergeguard analyze --post-comment
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

The CLI auto-detects the repository and PR number from the GitHub Actions environment.

## GitLab CI

```yaml
mergeguard:
  image: python:3.12-slim
  stage: test
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  script:
    - pip install py-mergeguard
    - mergeguard analyze --platform gitlab --post-comment
  variables:
    GITLAB_TOKEN: $CI_JOB_TOKEN
```

Pass `--platform gitlab` so MergeGuard uses the GitLab API. The `$CI_JOB_TOKEN` provides read access to the merge request; for write access (posting comments), create a project or group access token and store it as a CI/CD variable.

## Advanced Usage

### SARIF upload to GitHub Code Scanning

Upload MergeGuard results as SARIF so conflicts appear in the **Security** tab:

```yaml
- name: Run MergeGuard (SARIF)
  run: mergeguard analyze --format sarif > mergeguard.sarif
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: mergeguard.sarif
```

### Risk threshold gating

Fail the CI check when the risk score exceeds a threshold:

```yaml
- uses: Vansh2795/mergeguard@v1
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    risk-threshold: "50"
    fail-on-risk: "true"
```

Or with the pip-based approach:

```bash
SCORE=$(mergeguard analyze --format json | jq '.risk_score')
if [ "$SCORE" -ge 50 ]; then
  echo "Risk score $SCORE exceeds threshold" >&2
  exit 1
fi
```

### LLM-powered semantic analysis

Add an Anthropic API key to enable deeper semantic conflict detection:

```yaml
- uses: Vansh2795/mergeguard@v1
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

## GitHub Enterprise Server

For self-hosted GitHub instances, set the `github-url` action input or `MERGEGUARD_GITHUB_URL` environment variable:

```yaml
- uses: Vansh2795/mergeguard@v1
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    github-url: "https://github.example.com"
```

Or via CLI:

```bash
mergeguard --github-url https://github.example.com analyze --repo owner/repo --pr 42
```

## Bitbucket Pipelines

```yaml
pipelines:
  pull-requests:
    '**':
      - step:
          name: MergeGuard
          image: python:3.12-slim
          script:
            - pip install py-mergeguard
            - mergeguard analyze --platform bitbucket --post-comment
          variables:
            BITBUCKET_USERNAME: $BITBUCKET_USERNAME
            BITBUCKET_APP_PASSWORD: $BITBUCKET_APP_PASSWORD
```

## Environment Variables

See the [Configuration Guide](configuration.md) for the full list of environment variables and `.mergeguard.yml` options.
