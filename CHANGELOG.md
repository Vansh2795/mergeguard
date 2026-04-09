# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-08

### Overview

First stable release. MergeGuard detects cross-PR conflicts during development, before they reach your merge queue.

### Changed — Accuracy
- Fixed transitive conflict explosion: trimmed ambiguous module forms, limited BFS depth to 1, required symbol-level evidence for WARNING severity, added aggregation and global cap
- Benchmarked against FastAPI: 59-82% reduction in false positives
- Fixed multi-line Python import parsing for cross-file detection
- Fixed Go import regex scoping to import blocks only
- Fixed CODEOWNERS `**` glob matching

### Changed — Scope
- Secret scanning disabled by default (opt-in via `--secrets` flag)
- `scan-secrets` command hidden from default CLI help
- README rewritten with focused cross-PR conflict detection pitch

### Fixed — Security (19 critical/high findings)
- Git argument injection protection (`--` separators)
- ReDoS in Heroku/Slack secret patterns (bounded quantifiers)
- SSRF protection for webhook URLs (connect-time IP validation)
- XSS in SVG badges (XML escaping)
- Markdown injection in PR comments (sanitization)
- LLM prompt injection (XML delimiters around diff content)
- Token leakage via httpx repr (custom Auth classes)
- Bitbucket path traversal (URL encoding)
- GitLab POST/PUT rate limiting helpers

### Fixed — Reliability
- SQLite thread safety for webhook server
- Rate limiter crash on non-numeric headers
- AST RecursionError catch for deeply nested code
- Config retry fallback to defaults
- CLI resource leaks (client close on watch/auto-detect)
- Queue shutdown on full queue (non-blocking sentinel)
- Webhook rate limiter memory leak (periodic pruning)

### Added — Testing
- 695+ tests (up from ~600 in v0.5)
- Benchmark suite for measuring accuracy on real repos
- Coverage threshold enforced in CI (65%)
- Smoke tests for all output formatters

## [0.5.0] - 2026-03-26

### Added — v0.5: Secret Scanning
- Regex-based secret scanning for PR diffs — detects accidentally committed API keys, tokens, and private keys in added lines
- `ConflictType.SECRET` enum value for secret findings, surfaced as `CRITICAL` conflicts with inline annotations
- `SecretPattern` and `SecretsConfig` models with `enabled`, `use_builtin_patterns`, custom `patterns`, and `allowlist`
- 15 builtin patterns: AWS keys, GitHub PATs, GitLab PATs, Slack tokens/webhooks, Stripe/Twilio/SendGrid keys, private key headers, generic API keys/secrets, Heroku keys
- `scan_secrets()` function using `parse_unified_diff()` for accurate line numbers on added lines only
- Automatic redaction of secret values in descriptions (first 4 + last 3 chars)
- Deduplication per `(file, line, pattern_name)` to avoid duplicate findings
- Integrated into `_detect_all_conflicts()` — runs after guardrails, enabled by default
- `--secrets/--no-secrets` flag on `analyze` command to override config
- `scan-secrets` standalone CLI command with `--format terminal|json|sarif` output
- `SECRET` type label added to GitHub comment, inline annotation, and SARIF output formatters

### Added — v0.5: DORA Metrics
- DORA-style metrics tracking for conflict resolution: merge frequency, conflict rate, resolution times, and MTTRC
- `PRState` enum and `state`/`merged_at`/`closed_at` fields on `PRInfo` — populated by all three SCM clients (GitHub, GitLab, Bitbucket)
- `MetricsConfig` model with `enabled`, `retention_days`, and `time_windows` settings
- `MetricsSnapshot`, `DORAMetrics`, `DORAReport` models for metrics data
- `MetricsStore` — SQLite-backed storage for conflict snapshots with upsert, resolve, query, and pruning
- `record_analysis()` and `record_resolution()` functions in metrics engine
- `compute_dora_metrics()` — computes merge count, merges/day, conflict rate, mean/median/p90 resolution time, MTTRC, and unresolved count per time window
- `merged` field on `WebhookEvent` — populated from GitHub (`pr.merged`), GitLab (`action == "merge"`), Bitbucket (`event_key == "pullrequest:fulfilled"`)
- Webhook integration: snapshots recorded after analysis, resolutions recorded on CLOSED events
- Engine integration: snapshots recorded after `analyze_pr()` in both CLI and webhook flows
- `mergeguard metrics` CLI command with `--window`, `--format terminal|json|html` options
- REST endpoint `GET /api/metrics/dora/{owner}/{repo}` with configurable time windows
- Self-contained HTML report with Chart.js visualizations: summary cards, merge frequency chart, resolution time distribution, full metrics table

### Added — v0.5: Policy Engine
- Declarative policy engine with conditions-and-actions system for automated merge workflow decisions
- `PolicyConditionOp` enum: `gte`, `lte`, `eq`, `gt`, `lt`, `contains` (set membership), `matches` (glob patterns)
- `PolicyActionType` enum: `block_merge`, `require_reviewers`, `add_labels`, `notify_slack`, `notify_teams`, `post_comment`, `set_status`
- 13 field extractors: `risk_score`, `conflict_count`, `critical_count`, `warning_count`, `has_severity`, `has_conflict_type`, `affected_teams`, `ai_authored`, `files_changed`, `labels`, `author`, `file_count`, `lines_changed`
- `evaluate_policies()` evaluates all rules with AND-ed conditions and accumulates actions from matched policies
- `execute_policy_actions()` dispatches actions to SCM clients with graceful `hasattr` fallbacks
- `add_labels()` and `request_reviewers()` methods added to `SCMClient` protocol and all three platform clients (GitHub, GitLab, Bitbucket)
- `policy-check` CLI command with `--dry-run/--execute`, `--format terminal|json`, Rich table output
- Policy evaluation integrated into webhook handler (runs after merge queue status)
- `PolicyConfig` section in `.mergeguard.yml` for declarative policy definitions
- Audit trail in evaluation results (actual vs expected values per condition)
- Bitbucket `add_labels` gracefully no-ops with warning (unsupported by platform)

### Added — v0.5: Blast Radius Visualization
- Interactive D3.js force-directed graph visualization of PR conflict topology (`mergeguard blast-radius`)
- `BlastRadiusNode`, `BlastRadiusEdge`, `BlastRadiusData` models for graph data
- `build_file_dependency_graph()` public method on `MergeGuardEngine` for file-level dependency extraction
- Transitive blast radius computation via BFS on conflict adjacency graph
- Three output formats: HTML (interactive graph, default), terminal (Rich tables + ASCII adjacency), JSON (raw data)
- HTML features: zoom/pan, drag nodes, severity filtering, PR search, intra-stack toggle, stack cluster hulls, node/edge tooltips, detail sidebar, Shift+click file dependency expansion
- `--output` flag for writing HTML/JSON to file
- File-level dependency edges from import graph overlaid on conflict topology

### Added — v0.5: Stacked PR Support
- Stacked PR detection with three strategies: branch chain, label-based, and Graphite metadata
- `StackGroup` and `StackedPRConfig` models for stack configuration
- Automatic demotion of intra-stack conflicts from CRITICAL/WARNING to INFO severity
- Stack context in GitHub PR comments (stack banner with position indicator)
- Stack-aware merge ordering — enforces stack predecessor constraints
- Intra-stack conflicts excluded from merge queue blocking logic
- Collapsed intra-stack section in GitHub comments showing original severity
- Dimmed intra-stack display in terminal output
- Intra-stack prefix on inline review annotations
- `stacked_prs` configuration section in `.mergeguard.yml`

### Added — v0.5: Inline PR Annotations
- Inline PR annotations — conflict warnings posted as line-level review comments on the exact conflicting lines
- `post_pr_review()` method on SCMClient protocol (GitHub, GitLab, Bitbucket)
- `output/inline_annotations.py` formatter converting Conflicts to platform-agnostic ReviewComment objects
- `inline_annotations` config option in `.mergeguard.yml` (default: true)
- `--inline/--no-inline` CLI flag for `analyze` command
- Graceful degradation — summary comment still posts if review API permissions are missing
- Idempotent review posting — previous MergeGuard reviews are dismissed on re-analysis
- Conflict `source_lines` and `target_lines` now populated for all conflict types (HARD, BEHAVIORAL, INTERFACE, DUPLICATION)

### Added — v0.5: Webhook Server
- FastAPI webhook server for real-time conflict detection (`mergeguard serve`)
- Webhook endpoints: `/webhooks/github`, `/webhooks/gitlab`, `/webhooks/bitbucket`
- HMAC-SHA256 signature verification for all platforms
- Async background analysis queue with per-repo rate limiting and deduplication
- Targeted single-PR analysis mode (`analyze_pr_targeted()`) for webhook efficiency
- Prometheus metrics endpoint (`/metrics`) and health check (`/health`)
- `ServerConfig` model with `port`, `host`, `workers`, `analysis_timeout`, `queue_backend`
- Docker deployment support (Dockerfile + docker-compose.yml)
- `[server]` optional dependency group (fastapi, uvicorn)

### Added — v0.5: Merge Queue Integration
- Merge queue integration with commit status checks on all three platforms (GitHub, GitLab, Bitbucket)
- `MergeQueueConfig` model with `enabled`, `block_on_conflicts`, `block_severity`, `status_context`, `priority_labels`, `auto_recheck_on_close`
- `post_commit_status()` method added to `SCMClient` protocol and all platform clients
- `MergeReadiness` dataclass and `compute_merge_readiness()` function for merge blocking logic
- `MergeGroupEvent` model for handling GitHub `merge_group` webhook events
- `merge_group` webhook event parsing with PR number extraction from `head_ref` and commit messages
- Priority override via PR labels (`merge-priority:high` / `merge-priority:low`)
- Pending → success/failure status transitions during webhook analysis
- GitHub Action inputs: `merge-queue` and `block-severity`
- GitHub Action `merge_group` event support in `entrypoint.sh`
- Prometheus metrics: `statuses_posted`, `statuses_failed`, `merge_groups_analyzed`
- Graceful degradation on 401/403 for GitLab and Bitbucket status APIs

### Added — v0.5: CODEOWNERS-Aware Routing
- CODEOWNERS parser supporting GitHub and GitLab formats (`analysis/codeowners.py`)
- Auto-detection of CODEOWNERS file location (`.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS`)
- Last-match-wins pattern resolution (GitHub) and section-scoped matching (GitLab)
- `owners` field on `Conflict` model — code owners for each conflicting file
- `affected_teams` field on `ConflictReport` — aggregated list of all teams with conflicts
- `CodeownersConfig` model with `enabled`, `path`, and `team_channels` settings
- Owner @mentions in GitHub PR comments (both detailed and compact formats)
- Owner info in Slack and Teams notification payloads
- `notify_slack_per_team()` — targeted Slack notifications routed to team-specific channels
- Graceful degradation when CODEOWNERS file is missing

## [0.2.0] - 2026-03-15

### Added — v0.2: Accuracy & Core
- Cross-file symbol resolution for detecting conflicts across file boundaries via import graph analysis
- Cross-file call graph analysis in `SymbolIndex` for cross-module behavioral conflict detection
- Configurable risk score weights via `risk_weights` in `.mergeguard.yml` (must sum to ~1.0)
- Complete guardrail rule enforcement: `cannot_import_from`, `must_not_contain`, `max_function_lines`, `max_cyclomatic_complexity` (joining existing `max_files_changed`, `max_lines_changed`)
- Cyclomatic complexity computation via Tree-sitter AST branching node counting (10 languages)
- Configurable transitive conflict cap via `max_transitive_per_pair` (default: 5)
- Diff preview in terminal output with Rich syntax highlighting
- Holistic LLM analysis mode — batch conflict assessment for >3 conflicts per target PR
- PyYAML as a core dependency for reliable nested config parsing
- `cross_file`, `source_diff_preview`, `target_diff_preview` fields on `Conflict` model

### Added — v0.3: Enterprise Ready
- GitHub Enterprise Server support via `--github-url` / `github_url` config
- Bitbucket Cloud integration via REST API 2.0 (`--platform bitbucket`)
- Multi-repo analysis command (`mergeguard analyze-multi`)
- Merge order suggestion command (`mergeguard suggest-order`) — greedy algorithm on conflict-weighted graph
- Watch mode (`mergeguard watch`) — polls for PR changes, re-analyzes on `head_sha` changes
- Configurable performance constants: `max_file_size`, `max_diff_size`, `churn_max_lines`, `max_cache_entries`, `api_timeout`, `max_workers`
- Historical analysis and audit trail (`mergeguard history`)

### Added — v0.4: Community & Ecosystem
- MCP server with full implementations: `check_conflicts` (what-if analysis), `get_risk_score`, `suggest_merge_order`
- HTML report output (`--format html`) — self-contained with risk gauge, sortable table, syntax-highlighted diffs
- Static web dashboard (`mergeguard dashboard --format html`) — Chart.js visualizations with risk distribution, conflict types, collision matrix
- Slack webhook notifications (Block Kit) and Teams webhook notifications (Adaptive Cards)
- `mergeguard init` setup wizard — interactive config generation with language/workflow detection
- Community files: CHANGELOG, SECURITY, CODE_OF_CONDUCT, ROADMAP, GitHub issue/PR templates

### Changed
- Risk score weights are now configurable (previously hardcoded)
- Removed duplicate `DEFAULT_RISK_WEIGHTS` from `constants.py`
- Transitive conflict detection no longer capped at 1 per PR pair (configurable via `max_transitive_per_pair`)
- Config loader simplified to always use PyYAML (removed fragile fallback parser)
- Direction B transitive conflicts now deduplicated against Direction A results

## [0.1.2] - 2025-05-20

### Added
- Template-based fix suggestions (zero-cost, no API key required)
- LLM-enhanced fix suggestions with batch processing
- Owl mascot logos in README, docs, and PR comments
- Demo GIF for README

### Fixed
- Mypy type errors in engine.py and llm_analyzer.py
- Ruff format violations
- Removed unused imports
- Dropped Python 3.13 from CI (tree-sitter compatibility)

## [0.1.1] - 2025-05-18

### Added
- GitLab merge request support with SCMClient protocol
- SARIF output format for `analyze` command
- JSON output for `map` command
- CONTRIBUTING.md with development guide
- GitHub Action Docker support
- CI workflow and dogfood workflow

### Fixed
- GitHub Action entrypoint: handle float risk score
- Docker build context for PyPI installation
- CI workflow lint/type errors
- Symbol misattribution when new code inserted before existing symbols

### Changed
- Renamed package to `py-mergeguard` for PyPI availability

## [0.1.0] - 2025-05-15

### Added
- Initial release of MergeGuard
- Cross-PR conflict detection with 7 conflict types (HARD, INTERFACE, BEHAVIORAL, DUPLICATION, TRANSITIVE, REGRESSION, GUARDRAIL)
- Tree-sitter AST parsing for 14+ languages
- Composite risk scoring with 5 weighted factors
- GitHub REST API integration
- Rich terminal output with color-coded severity
- GitHub PR comment formatting
- AI authorship detection (commit messages, PR metadata, branch names)
- Dependency graph analysis for blast radius calculation
- Duplication detection via AST structure similarity
- Regression detection against decisions log
- Analysis caching (file-based JSON)
- `.mergeguard.yml` configuration support
- Click-based CLI (`analyze`, `map`, `dashboard`)

[0.5.0]: https://github.com/Vansh2795/mergeguard/compare/v0.2.0...v0.5.0
[0.2.0]: https://github.com/Vansh2795/mergeguard/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/Vansh2795/mergeguard/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Vansh2795/mergeguard/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Vansh2795/mergeguard/releases/tag/v0.1.0
