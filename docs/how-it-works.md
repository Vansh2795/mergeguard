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

### Step 5: Risk Scoring

The risk scorer (`risk_scorer.py`) computes a composite 0-100 score based on:
- **Conflict severity** (30%): critical=100, warning=50, info=15
- **Blast radius** (25%): how many downstream files depend on changed code
- **Pattern deviation** (20%): how much the code deviates from existing patterns
- **Churn risk** (15%): historically buggy files
- **AI attribution** (10%): AI-generated PRs get a modest penalty

### Step 6: Report

Results are formatted as:
- GitHub PR comments (with collapsible sections for low-severity issues)
- Terminal output (Rich-based colored tables)
- JSON reports (for CI integration)
- SVG badges (for README embedding)

## Supported Languages

MergeGuard uses Tree-sitter for AST parsing, supporting:
- Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, PHP, C/C++, C#, Swift, Kotlin

For unsupported languages, a regex-based fallback extracts function and class definitions.

## Data Flow Diagram

```
GitHub API → Fetch PRs → Parse Diffs → AST Analysis → Conflict Detection → Risk Scoring → Report
```

Each stage is independently testable and cacheable for performance.
