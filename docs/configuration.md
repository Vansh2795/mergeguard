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

### `max_transitive_per_pair` (default: `5`)

Maximum number of transitive conflicts to detect per PR pair. Increase to see the full blast radius; decrease to reduce noise.

```yaml
max_transitive_per_pair: 5
```

### `risk_weights` (default: built-in weights)

Custom weights for risk score computation. All 5 keys must be present and must sum to approximately 1.0 (0.95-1.05 tolerance).

```yaml
risk_weights:
  conflict_severity: 0.40
  blast_radius: 0.20
  pattern_deviation: 0.15
  churn_risk: 0.15
  ai_attribution: 0.10
```

### `github_url` (default: `null`)

GitHub Enterprise Server URL. Set this for self-hosted GitHub instances.

```yaml
github_url: "https://github.example.com"
```

### Performance Tuning

```yaml
max_file_size: 500000       # Skip files larger than this (bytes)
max_diff_size: 100000       # Skip diffs larger than this (bytes)
churn_max_lines: 500        # Normalization cap for churn risk factor
max_cache_entries: 500      # Max entries in content cache
api_timeout: 30             # API request timeout (seconds)
max_workers: 8              # Parallel enrichment workers
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

Guardrail rules for enforcing repository-specific policies. Each rule can target specific file patterns and enforce constraints. All 6 rule types are fully implemented:

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

  - name: "no-env-in-source"
    pattern: "src/**"
    must_not_contain:
      - "os.environ"
      - "process.env"
    message: "Use config module instead of reading env vars directly"

  - name: "no-god-functions"
    pattern: "src/**"
    max_function_lines: 50
    message: "Functions should not exceed 50 lines"

  - name: "complexity-limit"
    pattern: "src/**"
    max_cyclomatic_complexity: 10
    message: "Keep cyclomatic complexity under 10"
```

## Environment Variables

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub token for API access (required for GitHub) |
| `GITLAB_TOKEN` | GitLab token for API access (required for GitLab) |
| `BITBUCKET_USERNAME` | Bitbucket username for App Password auth |
| `BITBUCKET_APP_PASSWORD` | Bitbucket App Password |
| `ANTHROPIC_API_KEY` | Anthropic API key for LLM analysis (optional) |
| `OPENAI_API_KEY` | OpenAI API key for LLM analysis (optional) |
| `MERGEGUARD_CONFIG_PATH` | Override config file path |
| `MERGEGUARD_RISK_THRESHOLD` | Override risk threshold |
| `MERGEGUARD_MAX_OPEN_PRS` | Override max open PRs (safety cap) |
| `MERGEGUARD_MAX_PR_AGE_DAYS` | Override max PR age in days |
| `MERGEGUARD_GITHUB_URL` | GitHub Enterprise Server URL |

## GitHub Action Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `github-token` | Yes | — | GitHub token with PR read/write access |
| `anthropic-api-key` | No | — | Anthropic API key for LLM analysis |
| `risk-threshold` | No | `0` | Only comment if risk > threshold |
| `max-open-prs` | No | `200` | Max open PRs to analyze (safety cap) |
| `max-pr-age` | No | `30` | Only scan PRs updated within this many days |
| `config-path` | No | `.mergeguard.yml` | Path to config file |
| `github-url` | No | — | GitHub Enterprise Server URL |
