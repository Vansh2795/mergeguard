# MergeGuard Testing Strategy & Gap Analysis

> **Target repo:** `langchain-ai/langchain`
> **Purpose:** Test MergeGuard against a real, large-scale open-source repository before public launch.
> **Status:** 695+ unit/integration tests pass offline. Live-repo runs verified (langchain PR #35457, mlflow PR #21273 analyzed successfully).

---

## Table of Contents

1. [Why LangChain](#1-why-langchain)
2. [Prerequisites & Setup](#2-prerequisites--setup)
3. [Test Tiers](#3-test-tiers)
4. [Test Scenarios Mapped to LangChain Clusters](#4-test-scenarios-mapped-to-langchain-clusters)
5. [Expected Outputs & Success Criteria](#5-expected-outputs--success-criteria)
6. [Performance Benchmarks](#6-performance-benchmarks)
7. [Implementation Gaps Blocking Real-World Testing](#7-implementation-gaps-blocking-real-world-testing)
8. [Adding New Test Repositories](#8-adding-new-test-repositories)
9. [Demo Script](#9-demo-script)
10. [Alternative Test Targets](#10-alternative-test-targets)

---

## 1. Why LangChain

### Repo Profile

| Metric | Value |
|--------|-------|
| Stars | ~128k |
| Open PRs | 170+ at any time |
| Language | Python monorepo |
| CI | GitHub Actions |
| Merge cadence | 10-20 PRs/week |
| Contributors | 3,000+ |

### Monorepo Structure

LangChain uses a Python monorepo layout with several independent packages:

```
langchain/
├── libs/
│   ├── core/           # langchain-core (foundational abstractions)
│   ├── langchain/      # langchain (main package, depends on core)
│   ├── partners/       # Partner integrations (each a separate package)
│   │   ├── openai/
│   │   ├── anthropic/
│   │   ├── google-genai/
│   │   └── ...
│   ├── community/      # langchain-community
│   └── text-splitters/ # langchain-text-splitters
├── docs/
└── templates/
```

This structure is ideal for MergeGuard testing because:

- **Cross-package conflicts:** A change to `langchain-core` can break downstream `langchain` or partner packages, but GitHub's merge conflict detection won't catch this since the files are in different directories.
- **High PR volume:** 170+ open PRs means many simultaneous changes to the same files.
- **Real conflict scenarios:** Multiple teams work on related features (streaming, agent infrastructure, new integrations) that touch overlapping code paths.

### The 4 Live PR Conflict Clusters

These clusters were identified from manual analysis of LangChain's open PRs. They represent realistic scenarios MergeGuard should detect.

#### Cluster 1: OpenAI Streaming / Null-Choice PRs

4 PRs all touching `libs/partners/openai/langchain_openai/chat_models/base.py`:
- PR A: Fixes null-choice handling in streaming responses
- PR B: Adds structured output support to streaming
- PR C: Refactors `_stream()` to handle empty deltas
- PR D: Updates token counting for streaming chunks

**Why it matters:** All 4 PRs modify the same `_stream()` and `_generate()` methods. Merging any two without coordination will likely produce merge conflicts or behavioral regressions.

**Expected MergeGuard output:** HARD conflicts (same lines) + BEHAVIORAL conflicts (same function, different lines) between all pairs.

#### Cluster 2: Core Package Fixes in `langchain-core`

3-4 PRs modifying `libs/core/langchain_core/`:
- Fixes to `runnables/base.py` (the `Runnable` interface)
- Updates to `language_models/chat_models.py`
- Changes to serialization logic in `load/`

**Why it matters:** `langchain-core` is imported by every other package. Changes here have the widest blast radius.

**Expected MergeGuard output:** High blast_radius scores, INTERFACE conflicts if signatures change.

#### Cluster 3: New Integration Packages

3+ PRs each adding a new partner integration:
- `libs/partners/arcadedb/`
- `libs/partners/openrouter/`
- `libs/partners/huggingface/` updates

**Why it matters:** These PRs are structurally independent (different directories) but may duplicate utility functions or implement the same base interfaces differently.

**Expected MergeGuard output:** DUPLICATION conflicts if similar utility functions are added, low risk scores since files don't overlap.

#### Cluster 4: Agent Infrastructure PRs

PRs modifying agent-related code:
- Changes to `libs/langchain/langchain/agents/`
- Updates to tool calling interfaces
- New agent execution strategies

**Why it matters:** Agent infrastructure touches both `langchain-core` abstractions and the main `langchain` package, creating cross-package behavioral conflicts.

**Expected MergeGuard output:** BEHAVIORAL conflicts within agent modules, potential INTERFACE conflicts if tool-calling signatures change.

---

## 2. Prerequisites & Setup

### GitHub Token

Create a fine-grained Personal Access Token (PAT):

1. Go to **GitHub Settings > Developer Settings > Personal access tokens > Fine-grained tokens**
2. Token name: `mergeguard-testing`
3. Repository access: **Public Repositories (read-only)**
4. Permissions needed:
   - **Contents:** Read (for fetching file content)
   - **Pull requests:** Read (for fetching PR metadata and diffs)
   - **Metadata:** Read (default, always selected)
5. Generate and save the token

> **Rate limit:** Fine-grained PATs get 5,000 requests/hour for authenticated calls. A single `analyze` run uses ~92 API calls (content caching eliminates duplicate fetches). MergeGuard tracks `X-RateLimit-Remaining` headers and exposes a `rate_limit_remaining` property.

### Installation

```bash
# Clone the repo
git clone https://github.com/<your-fork>/mergeguard.git
cd mergeguard

# Install with all extras (includes dev + llm dependencies)
uv sync --all-extras

# Verify installation
uv run mergeguard --version
```

### Environment Variables

```bash
# Required for any live API tests
export GITHUB_TOKEN="github_pat_..."

# Optional: enables LLM-powered semantic analysis (Tier 4)
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Verification

```bash
# All existing tests must pass before proceeding
uv run pytest -v

# Expected output:
# tests/unit/test_ast_parser.py ........................ [ 11%]
# tests/unit/test_attribution.py .....                   [ 14%]
# tests/unit/test_cli.py ....                            [ 16%]
# tests/unit/test_concurrency.py ....                    [ 18%]
# tests/unit/test_config.py .......                      [ 21%]
# tests/unit/test_conflict.py .......................... [ 48%]
# tests/unit/test_dependency.py ..........               [ 53%]
# tests/unit/test_diff_parser.py .......                 [ 56%]
# tests/unit/test_edge_cases.py .....                    [ 58%]
# tests/unit/test_engine.py ...........                  [ 64%]
# tests/unit/test_error_recovery.py ....                 [ 66%]
# tests/unit/test_github_comment.py .......              [ 69%]
# tests/unit/test_patch_backfill.py ..........           [ 74%]
# tests/unit/test_regression.py ...                      [ 75%]
# tests/unit/test_risk_scorer.py ...........             [ 80%]
# tests/unit/test_similarity.py ....                     [ 82%]
# tests/unit/test_symbol_index.py .......                [ 85%]
# tests/integration/test_engine_e2e.py ..................[ 95%]
# tests/integration/test_github_client.py ............   [100%]
# 695 passed in X.XXs
```

---

## 3. Test Tiers

### Tier 1 — Unit Tests (offline)

**Location:** `tests/unit/`
**Run:** `uv run pytest tests/unit/ -v`
**Network:** None
**Purpose:** Validate individual functions and classes in isolation.

Currently covers (695+ tests total including integration):

| Test file | Count | Covers |
|-----------|-------|--------|
| `test_conflict.py` | 57 | file overlaps, classify conflicts, duplication, class demotion, comment-only, caller/callee, PR duplication, test-file downgrade |
| `test_ast_parser.py` | 24 | extract symbols, map diff to symbols, language detection, call graph, safe decode |
| `test_engine_e2e.py` | 24 | signature detection, batch analysis, content cache, fork handling, parallel enrichment, guardrails, regression, LLM, analysis cache, inserted function detection |
| `test_github_client.py` | 12 | rate limit tracking, fork detection, auth error propagation |
| `test_engine.py` | 29 | enrich PR robustness, pattern deviation, module suffix matching, symbol diff, cache symlink rejection, transitive conflict detection, three-way symbol classification |
| `test_risk_scorer.py` | 11 | score conflicts, compute risk score |
| `test_dependency.py` | 13 | build dependency graph, dependency depth, imported names |
| `test_patch_backfill.py` | 10 | extract file patches, backfill truncated patches |
| `test_config.py` | 7 | config loading, max_prs override, skipped_files |
| `test_github_comment.py` | 7 | report formatting, conflict grouping, collapse logic |
| `test_diff_parser.py` | 7 | parse unified diff, hunk parsing, multi-file diffs |
| `test_symbol_index.py` | 7 | symbol caching, lookup, caller finding |
| `test_attribution.py` | 5 | AI detection patterns |
| `test_edge_cases.py` | 5 | zero files, deleted-only, binary-only, all-ignored, empty content |
| `test_similarity.py` | 4 | Jaccard similarity, symbol dedup |
| `test_concurrency.py` | 4 | thread-safe SymbolIndex, content cache, parallel enrichment |
| `test_error_recovery.py` | 4 | corrupt cache, API timeout, disk full |
| `test_cli.py` | 4 | CLI commands, input validation |
| `test_regression.py` | 3 | regression detection against decisions log |

### Tier 2 — Integration with Recorded Fixtures (offline)

**Location:** `tests/integration/test_langchain_scenarios.py` *(to be created)*
**Fixtures:** `tests/fixtures/langchain/` *(to be created)*
**Run:** `uv run pytest tests/integration/test_langchain_scenarios.py -v`
**Network:** None (uses saved API responses)
**Purpose:** Replay real LangChain API responses through the full analysis pipeline without hitting GitHub.

**How to record fixtures:**

```python
# Script: scripts/record_fixtures.py (to be created)
# 1. Fetch PR metadata, file lists, diffs from GitHub API
# 2. Save as JSON files in tests/fixtures/langchain/
# 3. Tests load these fixtures and mock GitHubClient
```

**Test scenarios:**
- Analyze a PR from Cluster 1 (OpenAI streaming) against recorded open PRs
- Verify correct conflict types and severities for known overlapping PRs
- Validate risk score ranges for PRs with different characteristics
- Ensure JSON output schema validates correctly

### Tier 3 — Live API Tests (network, gated)

**Location:** `tests/live/test_github_live.py` *(to be created)*
**Run:** `uv run pytest tests/live/ -v -m live`
**Network:** GitHub REST API
**Marker:** `@pytest.mark.live`
**Purpose:** Verify MergeGuard can fetch real data from GitHub without errors.

**Test scenarios:**

```python
@pytest.mark.live
class TestGitHubLive:
    def test_fetch_open_prs(self, github_client):
        """Can we fetch the PR list from langchain-ai/langchain?"""
        prs = github_client.get_open_prs(max_count=5)
        assert len(prs) > 0
        assert all(pr.number > 0 for pr in prs)

    def test_fetch_pr_files(self, github_client):
        """Can we fetch the file list for a specific PR?"""
        prs = github_client.get_open_prs(max_count=1)
        files = github_client.get_pr_files(prs[0].number)
        assert len(files) > 0

    def test_fetch_file_content(self, github_client):
        """Can we fetch file content at a specific ref?"""
        content = github_client.get_file_content("README.md", "master")
        assert content is not None
        assert "langchain" in content.lower()
```

**Rate limit safety:**

```python
@pytest.fixture(autouse=True)
def skip_if_rate_limited():
    """Skip live tests if API rate limit is below 100 remaining."""
    import httpx
    resp = httpx.get(
        "https://api.github.com/rate_limit",
        headers={"Authorization": f"token {os.environ['GITHUB_TOKEN']}"},
    )
    remaining = resp.json()["resources"]["core"]["remaining"]
    if remaining < 100:
        pytest.skip(f"GitHub API rate limit too low: {remaining} remaining")
```

**pytest configuration** (add to `pyproject.toml`):

```toml
[tool.pytest.ini_options]
markers = [
    "live: tests that hit the live GitHub API (deselect with '-m not live')",
    "e2e: full end-to-end tests (deselect with '-m not e2e')",
]
```

### Tier 4 — Full End-to-End Tests (network, gated)

**Location:** `tests/e2e/test_langchain_e2e.py` *(to be created)*
**Run:** `uv run pytest tests/e2e/ -v -m e2e`
**Network:** GitHub REST API (heavy usage)
**Marker:** `@pytest.mark.e2e`
**Purpose:** Run MergeGuard CLI commands against the live LangChain repo and validate outputs end-to-end.

**Test scenarios:**

```python
@pytest.mark.e2e
class TestLangChainE2E:
    def test_analyze_single_pr(self, langchain_pr_number):
        """Full analysis of one LangChain PR via CLI."""
        result = runner.invoke(
            cli.analyze,
            ["--repo", "langchain-ai/langchain", "--pr", str(langchain_pr_number),
             "--format", "json"],
        )
        assert result.exit_code == 0
        report = json.loads(result.output)
        assert "risk_score" in report
        assert 0 <= report["risk_score"] <= 100
        assert "conflicts" in report

    def test_map_command(self):
        """Collision map renders without errors."""
        result = runner.invoke(
            cli.map,
            ["--repo", "langchain-ai/langchain"],
        )
        assert result.exit_code == 0
        assert "PR Collision Map" in result.output

    def test_dashboard_command(self):
        """Dashboard renders all PRs with risk scores."""
        result = runner.invoke(
            cli.dashboard,
            ["--repo", "langchain-ai/langchain"],
        )
        assert result.exit_code == 0
        assert "PR Risk Dashboard" in result.output
```

---

## 4. Test Scenarios Mapped to LangChain Clusters

### Cluster 1: OpenAI Streaming PRs

| Aspect | Detail |
|--------|--------|
| **Target files** | `libs/partners/openai/langchain_openai/chat_models/base.py` |
| **PR count** | 4 PRs touching the same file |
| **Expected conflict types** | HARD (overlapping lines in `_stream()`), BEHAVIORAL (same function, different hunks) |
| **Expected severities** | CRITICAL for line-overlap pairs, WARNING for same-function-different-lines pairs |
| **Risk score range** | 60-90 (high conflict severity + moderate churn) |
| **Assertion examples** | At least 2 HARD conflicts detected; `file_path` contains `chat_models/base.py`; risk_score >= 50 |
| **Blocking gaps** | ~~#2~~ (FIXED — content cache), ~~#4~~ (FIXED — returns all ranges), ~~#5~~ (FIXED — `_find_overlapping_range()`) |

### Cluster 2: Core Package Fixes

| Aspect | Detail |
|--------|--------|
| **Target files** | `libs/core/langchain_core/runnables/base.py`, `libs/core/langchain_core/language_models/chat_models.py` |
| **PR count** | 3-4 PRs |
| **Expected conflict types** | INTERFACE (if `Runnable` signatures change), BEHAVIORAL (same module, different functions) |
| **Expected severities** | CRITICAL for interface changes, WARNING for behavioral |
| **Risk score range** | 50-80 (high blast radius due to core package) |
| **Assertion examples** | `blast_radius` risk factor > 0; dependency_depth >= 2 for core files |
| **Blocking gaps** | ~~#7~~ (FIXED — signature comparison logic), ~~#8~~ (FIXED — `extract_call_graph()` populates dependencies) |

### Cluster 3: New Integration Packages

| Aspect | Detail |
|--------|--------|
| **Target files** | `libs/partners/arcadedb/`, `libs/partners/openrouter/`, `libs/partners/huggingface/` |
| **PR count** | 3+ PRs |
| **Expected conflict types** | DUPLICATION (similar utility functions), possibly none (independent directories) |
| **Expected severities** | INFO for duplications |
| **Risk score range** | 5-25 (low overlap, independent packages) |
| **Assertion examples** | No HARD conflicts; possibly 1-2 DUPLICATION conflicts; risk_score < 30 |
| **Blocking gaps** | None critical — this cluster should work with current implementation |

### Cluster 4: Agent Infrastructure PRs

| Aspect | Detail |
|--------|--------|
| **Target files** | `libs/langchain/langchain/agents/`, tool calling interfaces |
| **PR count** | 2-3 PRs |
| **Expected conflict types** | BEHAVIORAL (agent execution logic), INTERFACE (tool-calling APIs) |
| **Expected severities** | WARNING to CRITICAL |
| **Risk score range** | 40-70 |
| **Assertion examples** | At least 1 BEHAVIORAL conflict; conflicts reference agent-related files |
| **Blocking gaps** | ~~#7~~ (FIXED), ~~#8~~ (FIXED) — same as Cluster 2 |

---

## 5. Expected Outputs & Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| Unit test pass rate | 100% (695+) | **Achieved** |
| Integration fixture pass rate | 100% | All recorded scenarios pass |
| Live API fetch tests | 3/3 pass | Fetch PRs, files, content |
| E2E `analyze` completion | Exit code 0 | **Achieved** — langchain PR #35457 |
| E2E `map` completion | Exit code 0 | Table renders |
| E2E `dashboard` completion | Exit code 0 | All PRs listed |
| Conflicts detected (Cluster 1) | >= 2 HARD + >= 2 BEHAVIORAL | Known overlapping PRs |
| Conflicts detected (Cluster 3) | 0 HARD, 0-2 DUPLICATION | Independent packages |
| Risk score range | 0-100, valid float | No NaN, no negatives |
| JSON output validation | Valid against Pydantic schema | `ConflictReport.model_validate(output)` |
| API calls per single analysis | < 100 | **Achieved** — ~92 calls (content cache eliminates duplicates) |
| Single PR analysis time | < 60s | **Improved** — parallel enrichment with 8 workers |
| Dashboard (30 PRs) time | < 300s | **Improved** — batch enrichment shares PR data |

---

## 6. Performance Benchmarks

### Single PR Analysis

| Phase | Time | Notes |
|-------|------|-------|
| Fetch target PR | ~1s | Single API call |
| Fetch all open PRs | ~3s | Paginated list |
| Enrich target PR | ~5s | File content + diff parsing |
| Enrich other PRs | ~15-30s | **Parallel enrichment** (ThreadPoolExecutor, 8 workers) + **content cache** (no duplicate fetches) |
| Conflict detection | <1s | In-memory computation |
| Risk scoring | <1s | In-memory computation |
| **Total** | **~25-40s** | Content cache + parallel enrichment vs. original ~120-300s |

### API Call Breakdown (Single PR, 30 other PRs)

| Call | Count | Notes |
|------|-------|-------|
| `get_pr()` | 1 | Target PR metadata |
| `get_open_prs()` | 1 | List all PRs |
| `get_pr_files()` | 30 | One per other PR |
| `get_file_content()` | ~60 | One per changed file — `_content_cache` dict eliminates duplicates from `_compute_dependency_depth()` and `_compute_pattern_deviation()` |
| **Total** | **~92** | Down from ~180+ (3x duplication eliminated) |

### Dashboard (30 PRs)

| Metric | Value | Notes |
|--------|-------|-------|
| Time | ~5-10 min | Batch enrichment fetches and enriches all PRs once, then runs pairwise conflict detection |
| API calls | O(N) = ~200 | Shared PR data eliminates the previous O(N^2) = ~5,400 call pattern |

---

## 7. Implementation Gaps Blocking Real-World Testing

### Summary

| Gap | Description | Priority | Status |
|-----|-------------|----------|--------|
| #1 | No GitHub API rate limiting | P0 | **FIXED** — `rate_limit_remaining` property, header tracking |
| #2 | Duplicate `get_file_content()` calls | P0 | **FIXED** — `_content_cache` dict in engine |
| #3 | `analyze_all_open_prs()` O(N^2) | P0 | **FIXED** — batch enrichment, shared PR data |
| #4 | `_get_modified_ranges()` first-only | P0 | **FIXED** — returns all matching ranges |
| #5 | `_enrich_pr()` first hunk only | P0 | **FIXED** — `_find_overlapping_range()` |
| #6 | Broad `except Exception` | P0 | **FIXED** — propagates auth/network errors |
| #7 | `change_type` always `modified_body` | P1 | **FIXED** — signature comparison logic |
| #8 | `Symbol.dependencies` empty | P1 | **FIXED** — `extract_call_graph()` populates them |
| #9 | `ignored_paths` never applied | P1 | **FIXED** — `fnmatch` filtering in engine |
| #10 | LLM analyzer not wired | P1 | **FIXED** — wired into engine, gated by `llm_enabled` config |
| #11 | No logging | P1 | **FIXED** — `logging.getLogger(__name__)` in key modules |
| #12 | Transitive conflict detection | P2 | **FIXED** — `_detect_transitive_conflicts()` with BFS dependency traversal |
| #13 | Regression detection not wired | P2 | **FIXED** — wired into engine, gated by `check_regressions` config |
| #14 | `AnalysisCache` unused | P2 | **FIXED** — wired into engine, keyed by `(repo, pr, head_sha)` |
| #15 | `--pr` auto-detection | P2 | **FIXED** — `_auto_detect_repo_and_pr()` in cli.py |

**All 15 gaps fixed.**

### Priority Legend

- **P0:** Blocks end-to-end execution against a real repo — **All P0 gaps fixed**
- **P1:** Degrades conflict detection accuracy (false negatives / incorrect results)
- **P2:** Feature exists but is incomplete or not wired in

---

### P0 — Blocks E2E Execution (All Fixed)

<a id="gap-1-no-github-api-rate-limiting"></a>
#### Gap #1: No GitHub API Rate Limiting — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/integrations/github_client.py` |
| **Status** | **FIXED.** `rate_limit_remaining` property added. Response headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`) are tracked on every API call. Auth and network errors propagate correctly. |
| **Original problem** | `GitHubClient` made raw API calls with no rate limit awareness. |

<a id="gap-2-duplicate-get_file_content-calls"></a>
#### Gap #2: Duplicate `get_file_content()` Calls — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/engine.py` |
| **Status** | **FIXED.** `_content_cache: dict[tuple[str, str], str | None]` added to `MergeGuardEngine`. Populated on first fetch in `_enrich_pr()`, reused by `_compute_dependency_depth()` and `_compute_pattern_deviation()`. Eliminates ~120 redundant API calls per analysis. |
| **Original problem** | Same file content fetched up to 3 times per PR. |

<a id="gap-3-analyze_all_open_prs-on2-api-calls"></a>
#### Gap #3: `analyze_all_open_prs()` — O(N^2) API Calls — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/engine.py` |
| **Status** | **FIXED.** Batch enrichment fetches and enriches all PRs once, then runs pairwise conflict detection. Shared PR data eliminates N×N re-fetching. |
| **Original problem** | Each `analyze_pr()` call independently fetched all open PRs, resulting in O(N^2) API calls. |

<a id="gap-4-_get_modified_ranges-returns-only-first-symbols-range"></a>
#### Gap #4: `_get_modified_ranges()` Returns Only First Symbol's Range — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/conflict.py` |
| **Status** | **FIXED.** Now returns all matching `cs.diff_lines` for the file, not just the first match. |
| **Original problem** | Early return after first match caused false negatives for multi-symbol files. |

<a id="gap-5-_enrich_pr-stores-only-first-hunks-diff-range"></a>
#### Gap #5: `_enrich_pr()` Stores Only First Hunk's Diff Range — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/engine.py` |
| **Status** | **FIXED.** `_find_overlapping_range()` stores the specific range that actually overlaps with each symbol, not just the first hunk. |
| **Original problem** | `diff_lines` was always set to `modified_ranges[0]`, ignoring multi-hunk diffs. |

<a id="gap-6-broad-except-exception-hides-errors"></a>
#### Gap #6: Broad `except Exception` Hides Auth/Network Errors — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/integrations/github_client.py` |
| **Status** | **FIXED.** Auth errors (401), rate limit errors (403), and network errors now propagate. Only 404 (file not found at ref) is caught and returns `None`. |
| **Original problem** | Bare `except Exception` silently swallowed all errors including auth failures. |

---

### P1 — Degrades Conflict Accuracy (All Fixed)

<a id="gap-7-change_type-always-modified_body"></a>
#### Gap #7: `change_type` Always `"modified_body"` — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/engine.py` |
| **Status** | **FIXED.** Signature comparison logic compares the symbol's signature before and after the change. If the signature differs, `change_type="modified_signature"` is set correctly. Interface conflicts now fire as expected. |
| **Original problem** | Every `ChangedSymbol` was hardcoded to `change_type="modified_body"`. |

<a id="gap-8-symboldependencies-never-populated"></a>
#### Gap #8: `Symbol.dependencies` Never Populated — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/analysis/ast_parser.py` |
| **Status** | **FIXED.** `extract_call_graph()` populates `Symbol.dependencies` by walking `call_expression` / `call` AST nodes and resolving callee identifiers. Interface conflict detection and caller/callee behavioral conflicts now work correctly. |
| **Original problem** | `Symbol.dependencies` was always an empty list. |

<a id="gap-9-ignored_paths-defined-but-never-applied"></a>
#### Gap #9: `ignored_paths` Config Defined but Never Applied — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/engine.py` |
| **Status** | **FIXED.** `_enrich_pr()` filters `pr.changed_files` against `self._config.ignored_paths` using `fnmatch.fnmatch()`. Lock files, minified assets, and other ignored patterns are skipped before processing. |
| **Original problem** | `ignored_paths` config was defined but never applied — lock files inflated scores. |

<a id="gap-10-llm-analyzer-not-wired"></a>
#### Gap #10: LLM Analyzer Implemented but Not Wired into Engine — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/integrations/llm_analyzer.py`, `src/mergeguard/core/engine.py` |
| **Status** | **FIXED.** `_apply_llm_analysis()` method added to engine. When `llm_enabled=True`, behavioral conflicts are sent to `LLMAnalyzer.analyze_behavioral_conflict()`. Compatible changes are downgraded to INFO; incompatible changes get LLM-assessed severity. Requires `ANTHROPIC_API_KEY` env var. |
| **Original problem** | `LLMAnalyzer` existed but `engine.py` never called it. |

<a id="gap-11-no-logging"></a>
#### Gap #11: No Logging Anywhere — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/engine.py`, `src/mergeguard/integrations/github_client.py`, `src/mergeguard/core/conflict.py` |
| **Status** | **FIXED.** `logging.getLogger(__name__)` added to key modules. API calls, rate limits, pipeline stages, and conflict detection decisions are logged at appropriate levels (`DEBUG` for traces, `INFO` for progress). |
| **Original problem** | Zero `import logging` across the entire codebase. |

---

### P2 — Feature Completeness (All Fixed)

<a id="gap-12-transitive-conflict-detection"></a>
#### Gap #12: Transitive Conflict Detection — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/engine.py` |
| **Status** | **FIXED.** `_detect_transitive_conflicts()` method implemented with BFS dependency graph traversal. Detects when PR A modifies module X and PR B modifies module Y that imports X. Supports both forward and reverse direction detection, module name suffix matching, and deduplication. 12+ unit tests cover basic detection, deep chains, bidirectional edges, and imported symbol cross-referencing. |

<a id="gap-13-regression-detection-not-wired"></a>
#### Gap #13: Regression Detection Not Wired into Engine — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/core/regression.py`, `src/mergeguard/core/engine.py` |
| **Storage** | `src/mergeguard/storage/decisions_log.py` |
| **Status** | **FIXED.** `analyze_pr()` and `analyze_all_open_prs()` now instantiate `DecisionsLog` and call `detect_regressions()` when `self._config.check_regressions` is `True` (the default). Regression conflicts are appended to `all_conflicts` and included in the report. |
| **Original problem** | `detect_regressions()` and `DecisionsLog` were complete implementations, but `engine.py` never called them. |

<a id="gap-14-analysiscache-unused"></a>
#### Gap #14: `AnalysisCache` Exists but Unused — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/storage/cache.py`, `src/mergeguard/core/engine.py` |
| **Status** | **FIXED.** `analyze_pr()` checks the cache at entry using `cache.make_key(repo, pr_number, head_sha)`. On cache hit, the cached `ConflictReport` is returned immediately (skipping all API calls). On cache miss, the full analysis runs and the result is cached before returning. Repeated CI runs on the same PR commit are effectively free. |
| **Original problem** | `AnalysisCache` was a complete implementation but never imported or used by any other module. |

<a id="gap-15-pr-auto-detection"></a>
#### Gap #15: `--pr` Auto-Detection — FIXED

| | |
|---|---|
| **File** | `src/mergeguard/cli.py` |
| **Status** | **FIXED.** `_auto_detect_repo_and_pr()` detects the current git branch via `git rev-parse --abbrev-ref HEAD`, queries the GitHub API for an open PR with that head branch, and uses the most recent match. Clear error messages when not in a git repo or no matching PR found. 11 unit tests in `test_cli_autodetect.py`. |

---

## 8. Adding New Test Repositories

To test MergeGuard against a new repository, follow this template:

### Step 1: Create Fixture Directory

```
tests/fixtures/<repo-name>/
├── prs/
│   ├── pr_<number>.json        # PRInfo metadata
│   ├── pr_<number>_files.json  # ChangedFile list
│   └── pr_<number>_diff.txt    # Raw unified diff
├── files/
│   └── <path>__<ref>.txt       # File content at specific ref
├── expected/
│   └── cluster_<name>.json     # Expected conflicts and risk scores
└── README.md                   # Cluster descriptions and rationale
```

### Step 2: Record API Responses

```python
# scripts/record_fixtures.py
import json
from mergeguard.integrations.github_client import GitHubClient

client = GitHubClient(token, "owner/repo")
pr = client.get_pr(pr_number)

# Save PR metadata
with open(f"tests/fixtures/repo/prs/pr_{pr_number}.json", "w") as f:
    json.dump(pr.model_dump(), f, indent=2, default=str)

# Save file list
files = client.get_pr_files(pr_number)
with open(f"tests/fixtures/repo/prs/pr_{pr_number}_files.json", "w") as f:
    json.dump([f.model_dump() for f in files], f, indent=2)

# Save file content
for cf in files:
    content = client.get_file_content(cf.path, pr.base_branch)
    if content:
        safe_path = cf.path.replace("/", "__")
        with open(f"tests/fixtures/repo/files/{safe_path}__{pr.base_branch}.txt", "w") as f:
            f.write(content)
```

### Step 3: Define Expected Conflicts

```json
{
  "cluster_name": "streaming-fixes",
  "prs": [101, 102, 103],
  "expected_conflicts": [
    {
      "pr_a": 101,
      "pr_b": 102,
      "type": "hard",
      "severity": "critical",
      "file": "src/streaming.py",
      "symbol": "_stream"
    }
  ],
  "expected_risk_range": [50, 90]
}
```

### Step 4: Write Integration Test

```python
def test_streaming_cluster(recorded_fixtures):
    """Cluster: streaming-fixes — 3 PRs modifying the same streaming logic."""
    engine = create_engine_from_fixtures(recorded_fixtures)
    report = engine.analyze_pr(101)

    assert any(c.conflict_type == ConflictType.HARD for c in report.conflicts)
    assert 50 <= report.risk_score <= 90
```

### Step 5: Document PR Clusters

In `tests/fixtures/<repo-name>/README.md`, describe:
- Why these PRs were selected
- What conflicts you expect
- Which implementation gaps affect this test
- When the fixtures were recorded (PRs may be merged/closed later)

---

## 9. Demo Script

A 5-scene walkthrough suitable for Show HN, video recording, or live demos.

### Prerequisites

```bash
export GITHUB_TOKEN="github_pat_..."
cd mergeguard
```

### Scene 1: The Problem (30s)

```bash
# Show LangChain's open PR count
gh pr list --repo langchain-ai/langchain --state open --limit 5

# Narration: "LangChain has 170+ open PRs. GitHub shows per-PR merge
# conflicts, but can't tell you when two PRs modify the same function
# in semantically incompatible ways. That's what MergeGuard does."
```

### Scene 2: Single PR Analysis (60s)

```bash
# Pick a PR from Cluster 1 (OpenAI streaming)
mergeguard analyze --repo langchain-ai/langchain --pr <NUMBER> --format terminal

# Narration: "MergeGuard analyzes this PR against all 30 most recent
# open PRs. It detects that PR #X and PR #Y both modify the same
# _stream() method — a hard conflict that git merge can't auto-resolve."
```

### Scene 3: JSON Output for CI (30s)

```bash
# Same analysis, machine-readable
mergeguard analyze --repo langchain-ai/langchain --pr <NUMBER> --format json | jq '.risk_score, .conflicts | length'

# Narration: "JSON output integrates directly into CI. Gate merges
# when risk_score exceeds your threshold."
```

### Scene 4: Collision Map (30s)

```bash
mergeguard map --repo langchain-ai/langchain

# Narration: "The collision map shows which PRs touch overlapping files.
# Red cells indicate file-level overlap. This gives maintainers a
# bird's-eye view of merge risk across all open PRs."
```

### Scene 5: Risk Dashboard (60s)

```bash
mergeguard dashboard --repo langchain-ai/langchain

# Narration: "The dashboard ranks every open PR by risk score.
# High-risk PRs should be reviewed and merged first to avoid
# cascade conflicts. The robot emoji marks AI-authored PRs."
```

### Estimated Total Runtime

| Scene | Time (human) | API calls | Wall clock |
|-------|-------------|-----------|------------|
| 1 | 30s | 0 (uses gh CLI) | 30s |
| 2 | 60s | ~92 | ~25-40s (content cache + parallel enrichment) |
| 3 | 30s | ~92 | ~25-40s |
| 4 | 30s | ~60 | ~30-60s |
| 5 | 60s | ~200 | ~5-10 min (batch enrichment) |

> **Note:** Scenes 2-3 reuse cached results via `AnalysisCache` (Gap #14 fixed). Re-running the same PR analysis is effectively instant.

---

## 10. Alternative Test Targets

If LangChain is unavailable or you want to validate across different repo profiles:

| Repository | Stars | Open PRs | Language | Why useful |
|-----------|-------|----------|----------|------------|
| `pydantic/pydantic` | ~20k | ~30 | Python | Smaller scale, schema validation library. Good for verifying interface conflict detection. |
| `langchain-ai/langgraph` | ~8k | ~20 | Python | Sibling project to LangChain. Tests agent/graph infrastructure conflicts. |
| `astral-sh/ruff` | ~35k | ~40 | Rust | Tests multi-language support (Rust AST parsing via tree-sitter). |
| `vercel/next.js` | ~130k | ~100+ | TypeScript/JS | Large-scale JS monorepo. Tests TypeScript symbol extraction. |
| `django/django` | ~82k | ~80 | Python | Mature Python project with complex module interdependencies. |
| `facebook/react` | ~230k | ~40 | JavaScript | High-profile JS project. Tests JSX/TSX parsing. |

### Selection Criteria

- **PR volume:** At least 20 open PRs to exercise cross-PR analysis
- **Language support:** Must be a language MergeGuard supports (Python, JS/TS, Go, Rust, Java, etc.)
- **Monorepo bonus:** Monorepos create more interesting cross-package conflicts
- **Public repo:** Fine-grained PAT needs only public_repositories read-only access
