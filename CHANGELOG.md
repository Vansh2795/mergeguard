# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Vansh2795/mergeguard/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Vansh2795/mergeguard/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/Vansh2795/mergeguard/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Vansh2795/mergeguard/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Vansh2795/mergeguard/releases/tag/v0.1.0
