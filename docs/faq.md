# FAQ

## General

### What is MergeGuard?

MergeGuard is a cross-PR intelligence tool that detects conflicts between open pull requests before they become merge problems. It uses AST-level analysis to understand code changes at the function/class level, not just file-level overlap.

### How is this different from GitHub's built-in conflict detection?

GitHub only detects textual merge conflicts (same lines modified). MergeGuard detects semantic conflicts:
- Interface conflicts (signature changes affecting callers, including cross-file via import analysis)
- Behavioral conflicts (incompatible logic changes, including across file boundaries)
- Transitive conflicts (PR A changes a module that PR B depends on through imports)
- Duplications (same feature implemented twice)
- Regressions (re-introducing removed code)
- Guardrail violations (import restrictions, complexity limits, forbidden patterns)

### Does MergeGuard require AI/LLM?

No. LLM analysis is completely optional. The core conflict detection uses deterministic AST analysis with Tree-sitter. The optional LLM integration (Claude) adds semantic analysis for edge cases where AST analysis alone isn't sufficient.

### What languages are supported?

MergeGuard supports AST parsing for Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, PHP, C, C++, C#, Swift, and Kotlin. For unsupported languages, a regex-based fallback extracts basic function and class definitions.

## Setup & Configuration

### How do I set up MergeGuard?

The easiest way is as a GitHub Action. Add the workflow file to `.github/workflows/` and MergeGuard runs automatically on every PR. See [Getting Started](getting-started.md).

### What permissions does the GitHub token need?

The token needs `repo` scope (or `public_repo` for public repositories) to:
- Read pull request data and diffs
- Post comments on PRs
- Set commit statuses

### Can I use MergeGuard with private repositories?

Yes, as long as you provide a GitHub token with appropriate permissions.

### Does MergeGuard work with monorepos?

Yes. Use the `ignored_paths` config to scope analysis to specific directories, and the `rules` config to enforce module boundaries.

## Performance

### How long does analysis take?

For a single PR analysis against 30 open PRs: ~25-40 seconds. Parallel enrichment (8 workers) and content caching keep API calls to ~92 per analysis. For a full dashboard of 30 PRs, batch enrichment completes in ~5-10 minutes.

### Does MergeGuard hit GitHub API rate limits?

A single PR analysis uses ~92 API calls, well within the 5,000/hour limit for authenticated tokens. MergeGuard tracks `X-RateLimit-Remaining` headers and exposes a `rate_limit_remaining` property for monitoring.

## Troubleshooting

### MergeGuard shows false positives

Tune the `risk_threshold` in `.mergeguard.yml` to filter out low-confidence results. You can also add file patterns to `ignored_paths`.

### The risk score seems too high/low

The risk score is a composite of multiple factors. Check the `risk_factors` in the JSON report to understand which factors contribute most. You can customize the weights via `risk_weights` in `.mergeguard.yml` — see [Configuration](configuration.md).

### What platforms are supported?

MergeGuard supports GitHub (Cloud and Enterprise Server), GitLab (Cloud and self-hosted), and Bitbucket Cloud. Use `--platform` to select, or let MergeGuard auto-detect from your git remote.

### Can MergeGuard detect conflicts across different files?

Yes. MergeGuard uses import graph analysis to detect cross-file conflicts. If PR A changes `UserModel` in `models.py` and PR B imports `UserModel` in `views.py`, MergeGuard detects this as an interface or behavioral conflict depending on what changed.

### How do I get Slack/Teams notifications?

Configure webhook notifications in `.mergeguard.yml` or use the policy engine to trigger notifications based on conditions (e.g., notify Slack when risk score exceeds 80). CODEOWNERS-aware routing can send notifications to team-specific Slack channels. See the [Configuration Guide](configuration.md).

### What is the MCP server?

The MCP (Model Context Protocol) server lets AI agents like Claude query MergeGuard directly. It provides three tools: `check_conflicts` (what-if analysis before creating a PR), `get_risk_score` (risk assessment for an existing PR), and `suggest_merge_order` (optimal merge sequence). Install with `pip install py-mergeguard[mcp]`.

### How does secret scanning work?

MergeGuard scans only added lines in PR diffs using 15 builtin regex patterns (AWS keys, GitHub PATs, Slack tokens, etc.) plus custom patterns you define. Findings are surfaced as CRITICAL conflicts with inline annotations on the exact lines. Secret values are automatically redacted in all reports.

### What are stacked PRs?

Stacked PRs are PRs that build on each other (PR B is based on PR A's branch). MergeGuard detects stacks via branch chains, labels, or Graphite metadata and automatically demotes intra-stack conflicts to INFO since they're expected.

### How does the policy engine work?

The policy engine lets you define declarative rules with conditions and actions. For example, you can block merges when AI-authored PRs have critical conflicts, auto-label high-risk PRs, or require additional reviewers for infrastructure changes. Conditions evaluate fields like `risk_score`, `conflict_count`, `ai_authored`, etc.

### Can MergeGuard run as a webhook server?

Yes. `mergeguard serve` starts a FastAPI server that receives webhooks from GitHub, GitLab, and Bitbucket. It analyzes PRs in real-time on open/update events with HMAC-SHA256 signature verification. Deploy via Docker or `pip install py-mergeguard[server]`.
