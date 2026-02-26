# Architecture

## Project Structure

MergeGuard follows a src-layout with clear module boundaries:

```
src/mergeguard/
├── models.py          # Pydantic V2 data models (the "schema" of everything)
├── cli.py             # Click-based CLI entry point
├── config.py          # Configuration loader
├── constants.py       # Shared constants
├── core/              # Core analysis logic
│   ├── engine.py      # Main orchestrator
│   ├── conflict.py    # Conflict detection algorithm
│   ├── risk_scorer.py # Risk score computation
│   ├── regression.py  # Regression detection
│   └── guardrails.py  # Rule enforcement (V2)
├── analysis/          # Code analysis modules
│   ├── ast_parser.py  # Tree-sitter AST extraction
│   ├── symbol_index.py # Symbol caching
│   ├── dependency.py  # Import graph builder
│   ├── diff_parser.py # Unified diff parser
│   ├── attribution.py # AI code detection
│   └── similarity.py  # Duplication detection
├── integrations/      # External services
│   ├── github_client.py
│   ├── gitlab_client.py (V2)
│   ├── git_local.py
│   └── llm_analyzer.py
├── storage/           # Persistence
│   ├── decisions_log.py # SQLite decisions store
│   └── cache.py         # File-based cache
├── output/            # Report formatters
│   ├── github_comment.py
│   ├── badge.py
│   ├── json_report.py
│   └── terminal.py
└── mcp/               # AI agent integration (V2)
    └── server.py
```

## Design Principles

1. **Pydantic V2 throughout**: All data flows through typed Pydantic models. This provides validation, serialization, and IDE support.

2. **Lazy imports for optional deps**: `anthropic` and `mcp` are only imported when needed, with clear error messages if not installed.

3. **Pluggable VCS backends**: The GitHub client can be swapped for GitLab or local git operations.

4. **Cache-friendly**: Every analysis step can be cached by (file_path, ref) to avoid redundant work.

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

### Composite Risk Scoring
Weighted sum of 5 factors (conflict severity, blast radius, pattern deviation, churn risk, AI attribution), each normalized to 0-100.
