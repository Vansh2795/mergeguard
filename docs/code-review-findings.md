# Code Review Findings — April 2026

Comprehensive code review of the full MergeGuard codebase. Critical and high findings have a separate implementation plan at `docs/superpowers/plans/2026-04-04-critical-high-fixes.md`.

---

## Medium Severity

### M1. Bitbucket path traversal in `get_file_content`

**File:** `src/mergeguard/integrations/bitbucket_client.py:161`

`path` is interpolated directly into the URL without encoding. A path like `../../other-repo/file` could traverse outside the expected scope. GitLab correctly uses `urllib.parse.quote` — Bitbucket should do the same.

**Fix:** `url = f"{self._base_url}/src/{quote(ref, safe='')}/{quote(path, safe='/')}"`

---

### M2. MCP server: no input validation on `repo` parameter

**File:** `src/mergeguard/mcp/server.py:102-106`

The CLI validates repo format with `r"^[\w.-]+/[\w.-]+$"` but the MCP server does not validate the `repo` parameter at all.

**Fix:** Add the same regex validation before passing to SCM client constructors.

---

### M3. MCP server: no auth or rate limiting

**File:** `src/mergeguard/mcp/server.py` (entire file)

Any connected MCP client can trigger unlimited API calls using the server's tokens. A single `suggest_merge_order` call with a large repo could make hundreds of API requests.

**Fix:** Add configurable rate limits per MCP session. Consider requiring an API key for MCP connections.

---

### M4. Unescaped factor labels in HTML report

**File:** `src/mergeguard/output/html_report.py:218-223`

Factor `key` from `report.risk_factors` dict is used as an HTML label without `html.escape()`. If risk factors can be configured via `.mergeguard.yml`, this is an XSS vector.

**Fix:** Apply `html.escape()` to `label` at line 223.

---

### M5. Multi-line Python imports lose symbol names

**File:** `src/mergeguard/analysis/dependency.py:154,210-214`

The regex only matches single-line imports. Multi-line `from X import (\n    A,\n    B)` discards all imported names, weakening cross-file conflict detection.

**Fix:** When an opening paren is detected, continue reading subsequent lines until the closing paren, collecting all imported names.

---

### M6. `.tsx` files detected as TypeScript

**File:** `src/mergeguard/analysis/ast_parser.py:101-106`

The extension mapping iterates a dict where `.ts` appears before `.tsx`. Since `file.tsx` ends with `.ts`, it matches TypeScript instead of TSX.

**Fix:** Sort extensions by length (longest first) before matching, or use `os.path.splitext()`.

---

### M7. Go import regex matches arbitrary string literals

**File:** `src/mergeguard/analysis/dependency.py:163`

The pattern `r'"([\w./]+)"'` matches any double-quoted string in the file, not just import statements.

**Fix:** Scope the regex to match only within `import (...)` blocks or `import "..."` statements.

---

### M8. GitLab `request_reviewers` replaces rather than appends

**File:** `src/mergeguard/integrations/gitlab_client.py:286-289`

The PUT request sends only newly resolved `reviewer_ids`, replacing any existing reviewers.

**Fix:** Fetch current reviewer IDs from the MR first (like `add_labels` does at line 266), then merge before sending.

---

### M9. Webhook double-parse of request body

**File:** `src/mergeguard/server/webhook.py:556-565`

`request.json()` re-parses the body independently from the verified `body` bytes. Charset mismatches could mean the verified bytes differ from what's processed.

**Fix:** Replace `await request.json()` with `json.loads(body)` on lines 565, 595, and 624. *(Included in implementation plan as Task 15)*

---

### M10. `fnmatch` doesn't support `**` globs

**File:** `src/mergeguard/analysis/codeowners.py:148-158`

Python's `fnmatch` treats `*` as matching everything except `/`, so `**` recursive patterns silently fail to match.

**Fix:** Use `pathlib.PurePosixPath.match()` which supports `**`, or implement a custom matcher.

---

### M11. Merge group `#(\d+)` regex too broad

**File:** `src/mergeguard/server/events.py:68-69`

Matches any `#` followed by digits in commit messages, including issue references and markdown headings.

**Fix:** Use `r"Merge pull request #(\d+)"` or validate extracted numbers against actual open PRs.

---

### M12. `symbol_index.py` mutates cached Symbol objects in-place

**File:** `src/mergeguard/analysis/symbol_index.py:169`

`sym.dependencies` is mutated on cached Symbol objects. This persists and could cause incorrect results on repeated calls.

**Fix:** Remove the in-place mutation line — the cross-file call graph is returned as a separate data structure. *(Included in implementation plan as part of Task 7)*

---

### M13. `rate_limit.py` crashes on non-numeric header value

**File:** `src/mergeguard/integrations/rate_limit.py:29`

`int(remaining)` will raise `ValueError` on non-integer values like `"unlimited"` or `""`.

**Fix:** Wrap in `try/except ValueError: return`.

---

### M14. SQLite not thread-safe

**File:** `src/mergeguard/storage/decisions_log.py:19-24`

Single `sqlite3.Connection` shared without `check_same_thread=False`. Will raise `ProgrammingError` if used from webhook server worker threads.

**Fix:** Either `check_same_thread=False` with a threading lock, or create connections per operation.

---

### M15. Unbounded AST recursion

**File:** `src/mergeguard/analysis/ast_parser.py:152-264`

Recursive tree walkers (`_walk_tree`, `_collect_defined_names`, etc.) will hit Python's 1000-level recursion limit on deeply nested generated code.

**Fix:** Convert to iterative traversal with explicit stack, or catch `RecursionError`.

---

### M16. Config retry on ValidationError may itself raise

**File:** `src/mergeguard/config.py:58`

The retry after stripping unknown keys assumes all errors came from the unknown keys. Additional validation errors will raise unhandled.

**Fix:** Wrap the retry in its own try/except and fall back to defaults.

---

### M17. Bitbucket `get_open_prs` doesn't break on age cutoff

**File:** `src/mergeguard/integrations/bitbucket_client.py:96-99`

Uses `continue` instead of `break` when hitting stale PRs, iterating all pages unnecessarily.

**Fix:** Add `sort=-updated_on` to API params, change `continue` to `break`.

---

### M18. `compute_merge_readiness` recomputes full merge order every call

**File:** `src/mergeguard/core/merge_order.py:226`

O(n^2) when called per-PR in a batch.

**Fix:** Compute merge order once and pass it in, or cache the result.

---

### M19. GitLab `_get_all_diffs` called twice for same MR

**File:** `src/mergeguard/integrations/gitlab_client.py:113,122`

`get_pr_files()` and `get_pr_diff()` each fetch the diff independently.

**Fix:** Add LRU cache on `_get_all_diffs` keyed by `mr_iid`.

---

### M20. `ServerConfig.host` defaults to `0.0.0.0`

**File:** `src/mergeguard/models.py:333`

Binds to all interfaces by default — exposed to network if deployed without a reverse proxy.

**Fix:** Default to `127.0.0.1`.

---

## Low Severity

### L1. Dead code: `_format_conflict` never called — `github_comment.py:213`
### L2. Incorrect type annotation `ConflictReport | object` — `terminal.py:124`
### L3. Severity-color mismatch in dashboard pie chart — `dashboard_html.py:208`
### L4. `_percentile` reimplements `statistics.quantiles` — `metrics.py:39-49`
### L5. Risk score factor values not dampened to match total — `risk_scorer.py:111-113`
### L6. Duplicate severity rank mappings — `merge_order.py:17-21 vs 152`
### L7. `_is_comment_only_change` returns False for unknown extensions — `conflict.py:254`
### L8. `no_conflict_prs` can include PRs with guardrail/secret conflicts — `engine.py:1148-1154`
### L9. Guardrails `when` condition silently passes unknown values — `guardrails.py:41`
### L10. LRU cache TOCTOU race allows redundant API calls — `engine.py:195-211`
### L11. `_must_not_contain` uses substring match (not glob/regex) — `guardrails.py:172`
### L12. Policy `notify_slack/teams` called with empty webhook URL — `policy.py:337-339`
### L13. GitLab pagination could loop on unexpected `x-next-page` value — `gitlab_client.py:96-99`
### L14. GitHub `_map_status` silently defaults `"copied"` to MODIFIED — `github_client.py:321`
### L15. LLM clients have no request timeout — `llm_analyzer.py:195-207`
### L16. GitLab CODEOWNERS crash on malformed `[` section header — `codeowners.py:89`
### L17. Attribution confidence can accumulate >1.0 from marker files — `attribution.py:60-63`
### L18. `DecisionsLog.record_merge` is not atomic — `decisions_log.py:47-66`
### L19. Webhook SIGTERM handler can call `stop()` twice — `webhook.py:469,472`

---

## Test Suite Gaps

### Critical Coverage Gaps

| Module | Issue |
|--------|-------|
| `rate_limit.py` | Zero tests; contains `time.sleep()` that could hang tests |
| `git_local.py` | Zero tests for any git subprocess calls |
| `decisions_log.py` | Zero tests for SQLite persistence |
| `llm_analyzer.py` | Zero tests for prompt construction or response parsing |
| 6 output formatters | `terminal.py`, `json_report.py`, `html_report.py`, `dashboard_html.py`, `badge.py`, `metrics_html.py` — zero tests |
| `engine.analyze_pr()` | No integration test for full orchestration |
| `engine._detect_cross_file_conflicts()` | Untested critical path |

### Test Quality Issues

| Issue | Location |
|-------|----------|
| BitbucketClient missing from protocol compliance test | `test_protocol.py` |
| Bitbucket client has no HTTP-level tests (only static methods) | `test_bitbucket_client.py` |
| GitHub client tests use MagicMock instead of respx | `test_github_client.py` |
| Engine tests bypass `__init__` via `__new__`, fragile manual setup | `test_engine.py`, `test_edge_cases.py`, `test_concurrency.py` |
| CLI tests only check `--help` output | `test_cli.py` |
| `post_commit_status` untested for all 3 platforms | — |
| GitLab `post_pr_review` untested | — |
| No coverage configuration or minimum threshold | `pyproject.toml` |

### SCM Client Test Parity

| Method | GitHub | GitLab | Bitbucket |
|--------|--------|--------|-----------|
| `get_open_prs` | Tested | Tested | **Untested** |
| `get_pr` | Tested | Tested | **Untested** |
| `get_pr_files` | Tested | Tested | **Untested** |
| `get_pr_diff` | Tested | Tested | **Untested** |
| `get_file_content` | Tested | Tested | **Untested** |
| `post_pr_comment` | Tested | Tested | **Untested** |
| `post_pr_review` | Tested | **Untested** | **Untested** |
| `post_commit_status` | **Untested** | **Untested** | **Untested** |
| `add_labels` | Tested | **Untested** | Tested (no-op) |
| `request_reviewers` | Tested | **Untested** | **Untested** |
| Protocol compliance | Tested | Tested | **Untested** |
| Pagination | Untested | Tested | **Untested** |
