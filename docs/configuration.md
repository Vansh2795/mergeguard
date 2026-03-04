# Configuration

MergeGuard is configured via a `.mergeguard.yml` file in your repository root.

## All Options

### `risk_threshold` (default: `50`)

Only post a PR comment if the risk score exceeds this value. Set to `0` to always comment.

```yaml
risk_threshold: 50
```

### `check_regressions` (default: `true`)

Enable regression detection against recently merged PRs. When enabled, MergeGuard tracks significant decisions (removals, migrations, pattern changes) from merged PRs and flags open PRs that re-introduce removed patterns.

```yaml
check_regressions: true
```

### `max_open_prs` (default: `200`)

Safety cap on the number of open PRs to analyze. This is not the primary filter — use `max_pr_age_days` to control which PRs are scanned. This cap prevents runaway API usage on repositories with thousands of open PRs.

```yaml
max_open_prs: 200
```

### `max_pr_age_days` (default: `30`)

Only scan PRs that were updated within this many days. Since PRs are fetched sorted by most recently updated, MergeGuard stops iterating as soon as it encounters a PR older than this cutoff. This is the primary filter for controlling scan scope.

```yaml
max_pr_age_days: 30  # Scan PRs updated in the last month
```

### `decisions_log_depth` (default: `50`)

How many recently merged PRs to track for regression detection.

```yaml
decisions_log_depth: 50
```

### `llm_enabled` (default: `false`)

Enable LLM-powered semantic analysis using Claude. Requires an `ANTHROPIC_API_KEY` environment variable or the `anthropic-api-key` input in the GitHub Action.

When enabled, MergeGuard uses Claude to assess behavioral conflicts where AST analysis alone can't determine compatibility.

```yaml
llm_enabled: true
llm_model: "claude-sonnet-4-20250514"  # or any supported model
```

### `ignored_paths` (default: lock files)

File patterns to exclude from analysis. Supports glob patterns.

```yaml
ignored_paths:
  - "*.lock"
  - "*.min.js"
  - "*.min.css"
  - "package-lock.json"
  - "yarn.lock"
  - "pnpm-lock.yaml"
  - "poetry.lock"
  - "vendor/**"
  - "node_modules/**"
```

### `rules` (default: `[]`)

Guardrail rules for enforcing repository-specific policies. Each rule can target specific file patterns and enforce constraints.

```yaml
rules:
  - name: "no-cross-module-imports"
    pattern: "src/billing/**"
    cannot_import_from:
      - "src/auth/**"
    message: "Billing module must not import from auth module directly"

  - name: "ai-pr-size-limit"
    when: "ai_authored"
    max_files_changed: 20
    max_lines_changed: 500
    message: "AI-authored PRs are limited in scope for safety"

  - name: "no-god-functions"
    max_function_lines: 100
    message: "Functions should not exceed 100 lines"
```

## Environment Variables

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub token for API access (required) |
| `ANTHROPIC_API_KEY` | Anthropic API key for LLM analysis (optional) |
| `MERGEGUARD_CONFIG_PATH` | Override config file path |
| `MERGEGUARD_RISK_THRESHOLD` | Override risk threshold |
| `MERGEGUARD_MAX_OPEN_PRS` | Override max open PRs (safety cap) |
| `MERGEGUARD_MAX_PR_AGE_DAYS` | Override max PR age in days |

## GitHub Action Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `github-token` | Yes | — | GitHub token with PR read/write access |
| `anthropic-api-key` | No | — | Anthropic API key for LLM analysis |
| `risk-threshold` | No | `0` | Only comment if risk > threshold |
| `max-open-prs` | No | `200` | Max open PRs to analyze (safety cap) |
| `max-pr-age` | No | `30` | Only scan PRs updated within this many days |
| `config-path` | No | `.mergeguard.yml` | Path to config file |
