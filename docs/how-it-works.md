# How MergeGuard Works

MergeGuard uses a multi-stage analysis pipeline to detect conflicts between open pull requests.

## The Problem

When multiple developers (or AI agents) work on the same codebase simultaneously, their PRs can conflict in ways that git's merge algorithm won't catch:

- **Hard conflicts**: Two PRs modify the same function body at the same lines
- **Interface conflicts**: One PR changes a function signature while another calls it with the old signature
- **Behavioral conflicts**: Two PRs modify the same function at different lines, creating incompatible behavior
- **Duplications**: Two PRs implement the same feature independently
- **Regressions**: A PR re-introduces something that was recently removed

## Analysis Pipeline

### Step 1: Fetch PR Data

MergeGuard connects to the GitHub API and fetches:
- All open PRs with metadata (title, author, labels, branches)
- Changed files for each PR (with unified diffs)
- File contents at the base branch for AST parsing

PR enrichment runs in **parallel** using a ThreadPoolExecutor (8 workers), and a **content cache** (`_content_cache`) avoids duplicate `get_file_content()` calls across analysis phases. Fork PRs are detected automatically — MergeGuard skips head content fetches for forks since the head repo may not be accessible.

### Step 2: Parse Diffs

The unified diff parser (`diff_parser.py`) converts raw git diffs into structured data:
- File-level changes (added, modified, removed, renamed)
- Hunk-level details (line ranges, added/removed lines)
- Modified line ranges for each file

### Step 3: AST Analysis

Using Tree-sitter (`ast_parser.py`), MergeGuard parses source files and extracts:
- Function definitions with line ranges
- Class and method boundaries
- Symbol signatures (parameter lists, return types)
- Import/dependency relationships

The critical step here is **mapping diff line ranges to symbols**: "lines 45-67 were changed" becomes "the `getUserById` function was modified."

### Step 4: Conflict Detection

For each pair of open PRs (`conflict.py`):
1. Compute file overlap (which PRs touch the same files)
2. Compute symbol overlap (which PRs modify the same functions)
3. Classify conflicts by type and severity

### Step 4a: Cross-File Conflict Detection

MergeGuard goes beyond same-file conflicts by analyzing import graphs:
1. Build a dependency graph from all PR files using `extract_imports`
2. For each changed symbol in PR A, find all files that import it by name
3. If any of those importing files are changed by PR B, emit a cross-file conflict:
   - **INTERFACE** (CRITICAL) — when the changed symbol has a modified signature
   - **BEHAVIORAL** (WARNING) — when only the function body changed

This catches the most common real-world conflicts: PR A changes `User` class in `auth/models.py`, PR B calls `User` from `api/views.py`.

### Step 4b: Conflict Intelligence

After raw conflict detection, MergeGuard applies a severity intelligence pipeline to reduce noise and surface only actionable conflicts:

- **Test file demotion**: Conflicts in test files are demoted (CRITICAL→WARNING, WARNING→INFO) since test conflicts rarely block merges.
- **Comment-only change skipping**: When both sides only modify docstrings or comments, no behavioral conflict is reported — there's no risk of incompatible runtime behavior.
- **Class-level demotion**: CLASS-level symbol conflicts are demoted to INFO. Method-level conflicts within those classes capture the real risk more precisely.
- **Parent-class demotion**: When a method's parent class is also in the shared symbol set, the method conflict is demoted to INFO to avoid double-counting.
- **Caller/callee behavioral conflicts**: Detects when one PR modifies a function (callee) and another PR modifies a caller of that function. If the callee's signature is stable, the conflict is demoted to INFO.
- **PR-level duplication detection**: Compares PR titles/descriptions (Jaccard similarity) and file overlap percentages to flag potential duplicate PRs.
- **Same-file same-name duplication skip**: Prevents double-counting when a behavioral conflict already exists between the same symbols.
- **Both-sides-modify duplication skip**: Two PRs that both modify the same symbol body (`modified_body × modified_body`) are behavioral conflicts, not duplications.
- **Truncated patch backfill**: When GitHub truncates patches (>300 lines), MergeGuard fetches the full diff to ensure complete analysis.

### Step 5: Risk Scoring

The risk scorer (`risk_scorer.py`) computes a composite 0-100 score based on configurable weights:
- **Conflict severity** (default 30%): critical=100, warning=50, info=15
- **Blast radius** (default 25%): how many downstream files depend on changed code
- **Pattern deviation** (default 20%): how much the code deviates from existing patterns
- **Churn risk** (default 15%): historically buggy files
- **AI attribution** (default 10%): AI-generated PRs get a modest penalty

Teams can customize these weights via `.mergeguard.yml` — see [Configuration](configuration.md).

### Step 5b: Guardrail Enforcement

If guardrail rules are configured, MergeGuard enforces them:
- **`max_files_changed` / `max_lines_changed`** — PR size limits
- **`cannot_import_from`** — Forbidden import patterns (e.g., billing must not import auth)
- **`must_not_contain`** — Forbidden strings in added lines (e.g., `os.environ`)
- **`max_function_lines`** — Function length limits
- **`max_cyclomatic_complexity`** — Complexity limits computed via Tree-sitter AST

### Step 6: Report

Results are formatted as:
- GitHub/GitLab PR comments (with collapsible sections for low-severity issues)
- Terminal output (Rich-based colored tables with inline diff previews)
- JSON reports (for CI integration)
- SARIF v2.1.0 (for GitHub Code Scanning and other SARIF-aware CI tools)
- Self-contained HTML reports (with risk gauges, sortable tables, syntax-highlighted diffs)
- HTML dashboards (with Chart.js visualizations: risk distribution, conflict types, collision matrix)
- SVG badges (for README embedding)
- Slack/Teams webhook notifications (Block Kit / Adaptive Cards)

The `map` command also supports JSON output (`--format json`), emitting a machine-readable list of PR pairs and their shared files.

## Supported Languages

MergeGuard uses Tree-sitter for AST parsing, supporting:
- Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, PHP, C/C++, C#, Swift, Kotlin

For unsupported languages, a regex-based fallback extracts function and class definitions.

## Data Flow Diagram

```
SCM API → Fetch PRs → Parse Diffs → AST Analysis → Same-File Conflicts → Cross-File Conflicts → Transitive Conflicts → Guardrails → Risk Scoring → Report
  (GitHub/GitLab/Bitbucket)                            (symbol overlap)     (import graph)         (dependency chain)    (rules)
```

Each stage is independently testable and cacheable for performance.
