# FAQ

## General

### What is MergeGuard?

MergeGuard is a cross-PR intelligence tool that detects conflicts between open pull requests before they become merge problems. It uses AST-level analysis to understand code changes at the function/class level, not just file-level overlap.

### How is this different from GitHub's built-in conflict detection?

GitHub only detects textual merge conflicts (same lines modified). MergeGuard detects semantic conflicts:
- Interface conflicts (signature changes affecting callers)
- Behavioral conflicts (incompatible logic changes)
- Duplications (same feature implemented twice)
- Regressions (re-introducing removed code)

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

The risk score is a composite of multiple factors. Check the `risk_factors` in the JSON report to understand which factors contribute most.
