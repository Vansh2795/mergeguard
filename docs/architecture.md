# Architecture

## Project Structure

MergeGuard follows a src-layout with clear module boundaries:

```
src/mergeguard/
├── models.py          # Pydantic V2 data models (the "schema" of everything)
├── cli.py             # Click-based CLI entry point
├── config.py          # Configuration loader (YAML via PyYAML)
├── constants.py       # Shared constants
├── core/              # Core analysis logic
│   ├── engine.py          # Main orchestrator (same-file, cross-file, transitive)
│   ├── conflict.py        # Conflict detection algorithm
│   ├── risk_scorer.py     # Risk score computation (configurable weights)
│   ├── regression.py      # Regression detection
│   ├── guardrails.py      # Rule enforcement (6 rule types)
│   ├── merge_order.py     # Merge order suggestion algorithm
│   ├── policy.py          # Policy evaluation engine (conditions + actions)
│   ├── secrets.py         # Secret scanning logic
│   ├── secret_patterns.py # Builtin secret regex patterns
│   ├── metrics.py         # DORA metrics recording
│   └── fix_templates.py   # Fix suggestion templates
├── analysis/          # Code analysis modules
│   ├── ast_parser.py      # Tree-sitter AST extraction + cyclomatic complexity
│   ├── symbol_index.py    # Symbol caching + cross-file call graph
│   ├── dependency.py      # Import graph builder + symbol-level tracking
│   ├── diff_parser.py     # Unified diff parser
│   ├── attribution.py     # AI code detection
│   ├── similarity.py      # Duplication detection
│   ├── codeowners.py      # CODEOWNERS file parsing
│   └── stacked_prs.py     # Stacked PR detection
├── integrations/      # External services
│   ├── protocol.py        # SCMClient abstract protocol
│   ├── github_client.py   # GitHub Cloud + Enterprise Server
│   ├── gitlab_client.py   # GitLab Cloud + self-hosted
│   ├── bitbucket_client.py # Bitbucket Cloud REST API 2.0
│   ├── git_local.py       # Local git operations + auto-detection
│   ├── llm_analyzer.py    # Single + holistic batch analysis
│   └── rate_limit.py      # Rate limiting utilities
├── storage/           # Persistence
│   ├── decisions_log.py   # SQLite decisions store
│   ├── metrics_store.py   # SQLite metrics storage (DORA)
│   └── cache.py           # File-based cache
├── server/            # Webhook server
│   ├── webhook.py         # GitHub/GitLab/Bitbucket webhook handler
│   ├── queue.py           # Task queue with circuit breaker
│   ├── events.py          # Webhook event models
│   └── metrics.py         # Metrics endpoint handler
├── output/            # Report formatters
│   ├── github_comment.py      # Markdown PR comments
│   ├── terminal.py            # Rich terminal + diff previews
│   ├── inline_annotations.py  # Line-level review comments
│   ├── html_report.py         # Self-contained HTML report
│   ├── dashboard_html.py      # Chart.js dashboard
│   ├── blast_radius.py        # D3.js force-directed graph
│   ├── notifications.py       # Slack/Teams webhooks
│   ├── json_report.py
│   ├── sarif.py               # SARIF v2.1.0 formatter
│   ├── metrics_html.py        # DORA metrics HTML dashboard
│   └── badge.py               # SVG badge generation
└── mcp/               # AI agent integration
    └── server.py      # check_conflicts, get_risk_score, suggest_merge_order
```

## Design Principles

1. **Pydantic V2 throughout**: All data flows through typed Pydantic models. This provides validation, serialization, and IDE support.

2. **Lazy imports for optional deps**: `anthropic` and `mcp` are only imported when needed, with clear error messages if not installed.

3. **Pluggable VCS backends**: GitHub (Cloud + Enterprise), GitLab (Cloud + self-hosted), and Bitbucket Cloud are supported via an `SCMClient` protocol.

4. **Cache-friendly**: Every analysis step can be cached by (file_path, ref) to avoid redundant work. The engine maintains a `_content_cache` dict keyed by `(path, ref)` that eliminates duplicate `get_file_content()` calls across enrichment, dependency, and pattern analysis phases.

5. **Tree-sitter for AST parsing**: Supports 165+ languages with pre-compiled wheels (no C compiler needed).

## Data Models

All models live in `models.py` and form the backbone of the system:

- `PRInfo`: Represents a pull request with metadata and analysis data
- `ChangedFile`: A file modified in a PR
- `Symbol`: A named code entity (function, class, method)
- `ChangedSymbol`: A symbol modified in a PR
- `Conflict`: A detected conflict between two PRs
- `ConflictReport`: Full analysis report for a PR
- `MergeGuardConfig`: Configuration loaded from .mergeguard.yml

## Key Algorithms

### File Overlap Detection
O(n*m) comparison where n = files in target PR, m = files in other PRs. Uses set intersection for efficiency.

### Symbol-Level Conflict Detection
Maps diff line ranges to AST symbol boundaries. A "hard conflict" occurs when two PRs modify lines within the same symbol's range.

### Cross-File Conflict Detection
Uses the `DependencyGraph`'s symbol-level import tracking (`_symbol_forward` dict) to find conflicts across file boundaries. When PR A changes a symbol's signature and PR B's file imports that symbol by name, an INTERFACE conflict is emitted even though the PRs touch different files.

### Cross-File Call Graph
`SymbolIndex.build_cross_file_call_graph()` resolves function calls across files using import edges. This enables detection of behavioral conflicts where PR A modifies a function body and PR B calls it from another file.

### Cyclomatic Complexity Analysis
`compute_cyclomatic_complexity()` in `ast_parser.py` counts branching nodes (if/for/while/and/or/except/match) via Tree-sitter AST traversal, supporting 10 languages. Used by the `max_cyclomatic_complexity` guardrail rule.

### Parallel PR Enrichment
PR data enrichment (fetching files, parsing diffs, extracting symbols) runs in parallel using a ThreadPoolExecutor (configurable via `max_workers`, default 8). Combined with the content cache, this reduces single-PR analysis from ~120-300s to ~25-40s.

### Composite Risk Scoring
Weighted sum of 5 configurable factors (conflict severity, blast radius, pattern deviation, churn risk, AI attribution), each normalized to 0-100. Teams can override default weights via `risk_weights` in config.

### Merge Order Suggestion
Greedy algorithm that picks the PR with the lowest outgoing conflict weight at each step, recalculating after each "merge". Used by `mergeguard suggest-order` and the MCP `suggest_merge_order` tool.
