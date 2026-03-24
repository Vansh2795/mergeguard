# MergeGuard Code Audit: v0.5 Comprehensive Review

> **Date:** 2026-03-23
> **Scope:** Full codebase — `src/mergeguard/`, `tests/`, `action/`, `Dockerfile`
> **Prior audit:** 2026-03-03 (44 findings, 38 resolved, 6 deferred)
> **This audit:** 80 new findings across 7 categories

---

## Previous Audit Status

The March 3 audit found 44 issues and resolved 38 across phases 1-5. 6 were intentionally deferred (S-7, S-9, P-8, P-10, Q-6, Q-7). This audit builds on that work and covers new code added since (secrets scanning, DORA metrics, policy engine, MCP server, webhook server, blast radius, stacked PRs, notifications).

---

## Summary

| Category | P0 | P1 | P2 | P3 | Total |
|----------|----|----|----|----|-------|
| [Security](#1-security) | 1 | 5 | 4 | 3 | **13** |
| [Reliability](#2-reliability) | 1 | 4 | 2 | 1 | **8** |
| [Performance](#3-performance) | 0 | 3 | 10 | 5 | **18** |
| [Quality](#4-quality) | 0 | 2 | 8 | 3 | **13** |
| [Improvement](#5-improvement) | 0 | 2 | 6 | 3 | **11** |
| [Testing](#6-testing) | 0 | 0 | 1 | 0 | **1** |
| [Cleanup](#7-cleanup) | 0 | 0 | 2 | 7 | **9** |
| **Total** | **2** | **16** | **33** | **22** | **73** |

Legend: **P0** = fix before any deployment, **P1** = fix before production, **P2** = fix soon after launch, **P3** = nice-to-have / tech debt

---

## 1. Security

### SEC-01: Webhook authentication bypass when secret is not configured (P0)

**Files:** `src/mergeguard/server/webhook.py:389-392, 418-421, 445-448`

All three webhook endpoints skip signature verification when the corresponding env var is empty:

```python
secret = os.environ.get("MERGEGUARD_WEBHOOK_SECRET_GITHUB", "")
if secret and not verify_github_signature(body, x_hub_signature_256, secret):
    ...
```

With no secret configured (the default), anyone can send forged payloads to trigger analysis, post PR comments, commit statuses, and Slack notifications with attacker-controlled content.

**Fix:** Reject requests when no secret is configured, or at minimum fail-open with a loud startup warning. Default to "reject" not "accept."

---

### SEC-02: SSRF via user-controllable notification webhook URLs (P1)

**Files:** `src/mergeguard/output/notifications.py:124, 220, 321`, `src/mergeguard/core/policy.py:336, 342`

Slack/Teams notification functions call `httpx.post(webhook_url, ...)` with zero URL validation. The `webhook_url` comes from `.mergeguard.yml` (controlled by PR authors). An attacker could set it to `http://169.254.169.254/latest/meta-data/` or an internal endpoint.

**Fix:** Validate URLs against expected patterns (e.g., must be `https://hooks.slack.com/` for Slack). Block RFC 1918 and link-local addresses.

---

### SEC-03: SSRF via GitHub Enterprise / GitLab base URLs leaking API tokens (P1)

**Files:** `src/mergeguard/integrations/github_client.py:47-55, 127`, `src/mergeguard/integrations/gitlab_client.py:44-46`, `src/mergeguard/server/webhook.py:299, 308`

The `github_url` field in `.mergeguard.yml` (line 536 of `models.py`) controls the base URL for all API requests. The `Authorization: token {self._token}` header is sent to whatever host this points to. An attacker who modifies the config file in a PR could redirect API calls to their server and steal the token.

**Fix:** Never send API tokens to config-file-sourced URLs without host validation. Environment-variable-sourced URLs are lower risk.

---

### SEC-04: MCP server accepts GitHub tokens as tool parameters (P1)

**Files:** `src/mergeguard/mcp/server.py:63-68, 152-156, 203-206`

```python
async def check_conflicts(repo: str, files: list[str], token: str) -> dict[str, Any]:
```

Tokens are passed through the MCP protocol in plain text, end up in conversation history, logs, and potentially third-party tool systems.

**Fix:** Read tokens from environment variables within the tool implementation.

---

### SEC-05: Shell injection risk in GitHub Action entrypoint (P1)

**Files:** `action/entrypoint.sh:10, 57, 83, 128-133`

Unquoted variable expansions and string-interpolated JSON in curl commands:

```bash
REPORT=$(mergeguard $GLOBAL_OPTS analyze $ANALYZE_OPTS 2>/dev/null || echo '{"conflicts":[]}')
curl ... -d "{\"state\":\"$state\",\"description\":\"${description:0:140}\"}"
```

A repo name or description containing shell metacharacters or `"` could break the JSON or cause injection.

**Fix:** Quote all variable expansions. Use `jq --arg` to construct JSON payloads.

---

### SEC-06: Docker image runs as root (P1)

**File:** `Dockerfile`

The container never creates a non-root user. The webhook server runs as root inside the container.

**Fix:** Add `RUN useradd -m mergeguard` and `USER mergeguard` before the entrypoint.

---

### SEC-07: ReDoS risk in user-supplied secret patterns (P2)

**Files:** `src/mergeguard/core/secrets.py:66-70`, `src/mergeguard/core/secret_patterns.py:53`

User-supplied patterns from `.mergeguard.yml` are compiled with `re.compile()` with no timeout or complexity check. The builtin Heroku pattern also uses `.*` which can backtrack on long lines.

**Fix:** Use `re.compile(pattern)` with timeout (Python 3.12+), or use `re2`. At minimum, wrap `regex.search()` calls with a timeout.

---

### SEC-08: No rate limiting on webhook endpoints (P2)

**File:** `src/mergeguard/server/webhook.py`

No request rate limiting. Combined with SEC-01, an attacker could flood the server with forged events, exhausting GitHub API rate limits and triggering excessive notifications.

**Fix:** Add FastAPI rate limiting middleware (e.g., `slowapi`). Rate-limit by source IP or repository.

---

### SEC-09: Git ref injection in local git operations (P2)

**Files:** `src/mergeguard/integrations/git_local.py:64-77`

User-controlled strings (`base`, `head`, `ref`, `path`) are passed directly to git commands. A `ref` starting with `-` could be interpreted as a git flag.

**Fix:** Validate that ref/base/head params don't start with `-`. Use `--` separator where possible.

---

### SEC-10: Token potentially logged in HTTP error tracebacks (P2)

**File:** `src/mergeguard/integrations/github_client.py:122-131`

The `Authorization` header is passed per-request. On `raise_for_status()`, httpx may include full request details (including the token) in the exception message.

**Fix:** Set the Authorization header on the `httpx.Client` at construction time. Catch `HTTPStatusError` and re-raise with sanitized details.

---

### SEC-11: Unauthenticated health/metrics endpoints expose internal state (P3)

**File:** `src/mergeguard/server/webhook.py:360-377`

`/health` and `/metrics` expose uptime, queue depth, analysis counts, and timing data without authentication.

**Fix:** Put behind basic auth or restrict to internal networks.

---

### SEC-12: Secret redaction reveals too many characters (P3)

**File:** `src/mergeguard/core/secrets.py:33-37`

`_redact()` shows first 4 + last 3 characters (7 of 20 chars for AWS keys). For short secrets this is a significant portion.

**Fix:** Show fewer characters or just the pattern name.

---

### SEC-13: Unbounded `_pending` dict in analysis queue (P3)

**File:** `src/mergeguard/server/queue.py:83-85`

The deduplication dict grows without bound. Keys are only removed when tasks complete. If events arrive faster than they're processed, memory grows.

**Fix:** Add a size limit or periodic pruning.

---

## 2. Reliability

### REL-01: httpx.Client never closed — connection leak in all SCM clients (P0)

**Files:** `src/mergeguard/integrations/github_client.py:56`, `src/mergeguard/integrations/gitlab_client.py:47`, `src/mergeguard/integrations/bitbucket_client.py:49`

All three clients create `httpx.Client()` in `__init__` but have no `close()`, `__enter__`, or `__exit__`. The `SCMClient` protocol also lacks `close()`. In the long-running webhook server, TCP connections leak indefinitely.

**Fix:** Add `close()` to the `SCMClient` protocol. Implement `__enter__`/`__exit__` on all clients. Ensure the engine and webhook handler call cleanup.

---

### REL-02: No retry logic for GitLab and Bitbucket clients (P1)

**Files:** `src/mergeguard/integrations/gitlab_client.py`, `src/mergeguard/integrations/bitbucket_client.py`

GitHub client has retry via `GithubRetry`, but GitLab and Bitbucket use raw `httpx.Client` with no retry. Transient 5xx and connection resets fail immediately.

**Fix:** Use `httpx.HTTPTransport(retries=3)` or `tenacity`.

---

### REL-03: `assert` statements in production code — 7 instances (P1)

**Files:**
- `src/mergeguard/server/webhook.py:401, 430, 457` — `assert _queue is not None`
- `src/mergeguard/core/guardrails.py:198, 235` — `assert max_lines/max_complexity is not None`
- `src/mergeguard/core/engine.py:185` — `assert token is not None`
- `src/mergeguard/output/inline_annotations.py:52` — `assert conflict.source_lines is not None`

All stripped under `python -O`. The webhook ones are particularly dangerous — a race could leave `_queue` as `None`, causing silent `NoneType` crashes.

**Fix:** Replace with `if x is None: raise RuntimeError("...")`.

---

### REL-04: No circuit breaker for API outages (P1)

**File:** `src/mergeguard/server/webhook.py`

When GitHub is down, every webhook queues an analysis that immediately fails. The queue worker keeps trying, logging errors at high volume with no cooldown.

**Fix:** Implement a circuit breaker that detects repeated failures and stops making calls for a cooldown period.

---

### REL-05: No graceful shutdown — no SIGTERM handler (P1)

**File:** `src/mergeguard/server/webhook.py`

No signal handler to stop accepting new webhooks before draining. In Kubernetes (30s SIGTERM grace), the server should return 503 on new requests and drain the queue. The `_shutting_down` flag exists but nothing prevents new enqueue calls during shutdown.

**Fix:** Add SIGTERM handler that sets `_shutting_down`, returns 503 on new requests, and drains with a configurable timeout.

---

### REL-06: No drain timeout on queue shutdown (P2)

**File:** `src/mergeguard/server/queue.py:63-69`

`AnalysisQueue.stop()` puts a sentinel and awaits the worker. If mid-analysis (up to 300s), shutdown hangs for 5 minutes.

**Fix:** Add configurable drain timeout, after which in-flight work is abandoned.

---

### REL-07: ThreadPoolExecutor timeout has no partial-result recovery (P2)

**File:** `src/mergeguard/core/engine.py:353, 473, 533`

`as_completed(futures, timeout=300)` on timeout raises `TimeoutError` that crashes the entire analysis. If 1 of 200 PRs hangs, all fail.

**Fix:** Catch per-future `TimeoutError`, log it, and continue with partial results.

---

### REL-08: Rate limiting is reactive only (P3)

**Files:** All three SCM client `_check_rate_limit` methods

Rate limit handling only kicks in when `remaining < 10`. No proactive throttling. Analyzing 200 PRs fires 600+ API calls in rapid succession, which can exhaust the quota before the check triggers.

**Fix:** Query remaining quota upfront and throttle accordingly.

---

## 3. Performance

### PERF-01: Synchronous engine call blocks async webhook handler (P1)

**File:** `src/mergeguard/server/webhook.py:186-204`

`_handle_analysis()` is `async` but calls `engine.analyze_pr()` synchronously — blocking the asyncio event loop. Because there's one queue worker, all webhook processing is serialized and blocking.

**Fix:** Wrap in `asyncio.to_thread()` (the MCP server already does this at `mcp/server.py:149`).

---

### PERF-02: Blocking `time.sleep()` in rate limit handlers called from async context (P1)

**Files:** `src/mergeguard/integrations/github_client.py:256`, `gitlab_client.py:308`, `bitbucket_client.py:323`

All three clients use `time.sleep(min(wait, 300))` when rate limits are low. When called from the webhook server path (via ThreadPoolExecutor), this blocks the worker thread for up to 300 seconds.

**Fix:** Cap sleep at 30s. For async paths, use `asyncio.sleep()` or async HTTP clients.

---

### PERF-03: N+1 API pattern in MCP `check_conflicts` tool (P1)

**File:** `src/mergeguard/mcp/server.py:107-121`

Fetches all open PRs, then loops calling `client.get_pr_files(pr.number)` for each one. 50 open PRs = 51 sequential API calls.

**Fix:** Use `ThreadPoolExecutor` to fetch PR files in parallel. Short-circuit once all target files are matched.

---

### PERF-04: O(N*M) duplication detection with no short-circuit (P2)

**File:** `src/mergeguard/analysis/similarity.py:52-84`

Nested loop over all symbols from both PRs. `_tokenize_signature()` (line 87-92) also has `import re` inside the function body and uses an uncompiled pattern.

**Fix:** Pre-compile regex at module level. Group symbols by `symbol_type` to reduce comparison space.

---

### PERF-05: `list.pop(0)` in BFS — O(N) per dequeue (P2)

**File:** `src/mergeguard/analysis/dependency.py:80, 96, 123`

Three BFS implementations use `list.pop(0)` which shifts all elements. Degrades BFS from O(V+E) to O(V^2). The codebase already uses `deque` correctly in `blast_radius.py:69`.

**Fix:** Use `collections.deque` with `popleft()`.

---

### PERF-06: Duplicate dependency graph construction (P2)

**File:** `src/mergeguard/core/engine.py:970, 750`

`_detect_cross_file_conflicts()` builds a dependency graph at line 970, then `_detect_transitive_conflicts()` builds another at line 750. Both fetch the same file contents and parse the same imports twice.

**Fix:** Build the graph once and pass to both methods.

---

### PERF-07: Regex compiled inside hot loops (P2)

**Files:** `src/mergeguard/analysis/similarity.py:87-92`, `src/mergeguard/analysis/ast_parser.py:654-691`

`_tokenize_signature()` uses `re.findall(r"\w+", ...)` inside the O(N*M) duplication loop. `_fallback_extract()` compiles two regex patterns on every call.

**Fix:** Pre-compile all patterns as module-level constants.

---

### PERF-08: Tree-sitter parser re-created on every file (P2)

**File:** `src/mergeguard/analysis/ast_parser.py:116, 283, 324, 605`

`get_parser()` is called every time `extract_symbols()` etc. is invoked. `compute_cyclomatic_complexity()` calls it per-function in guardrails checking.

**Fix:** Cache parser instances per language in a module-level dict.

---

### PERF-09: Sequential LLM calls for individual conflicts (P2)

**File:** `src/mergeguard/core/engine.py:1224-1267`

Individual behavioral conflicts are analyzed one at a time. Each LLM call adds 1-5 seconds of latency.

**Fix:** Batch LLM calls using `ThreadPoolExecutor` or `asyncio.gather()`.

---

### PERF-10: O(N*M*K) interface conflict check (P2)

**File:** `src/mergeguard/core/conflict.py:457-491`

For each target symbol, iterates over all other symbols checking `if cs.symbol.name in other_cs.symbol.dependencies` — where `dependencies` is a `list[str]`, making `in` check O(K).

**Fix:** Pre-build a set of all dependency names: `all_deps = {dep for ocs in other_pr.changed_symbols for dep in ocs.symbol.dependencies}`.

---

### PERF-11: Sequential merge group analysis (P2)

**File:** `src/mergeguard/server/webhook.py:132-137`

Each PR in a merge group is analyzed sequentially. 5 PRs = 5x latency.

**Fix:** Analyze PRs in parallel with `asyncio.gather()` + `asyncio.to_thread()`.

---

### PERF-12: Config reloaded from disk on every webhook event (P2)

**File:** `src/mergeguard/server/webhook.py:178`

`load_config()` reads and parses `.mergeguard.yml` from disk on every single webhook event.

**Fix:** Load once at startup. Cache with file-mtime invalidation for hot-reload.

---

### PERF-13: Missing `per_page` on GitHub PR fetch (P2)

**File:** `src/mergeguard/integrations/github_client.py:61-93`

PyGithub defaults to 30 items per page. Fetching 200 PRs requires ~7 API calls instead of 2 with `per_page=100`.

**Fix:** Pass `per_page=100` to `get_pulls()`.

---

### PERF-14: Double `splitlines()` in diff preview (P3)

**File:** `src/mergeguard/core/conflict.py:628-640`

`cf.patch.splitlines()[:10]` and `len(cf.patch.splitlines()) > 10` — splitting the same string twice. Same pattern in GitLab client at line 383-393.

**Fix:** Split once, store the result.

---

### PERF-15: Per-record SQLite COMMIT (P3)

**File:** `src/mergeguard/storage/metrics_store.py:89, 105`

`record_snapshot()` commits after every upsert. Batch scenarios create many small transactions with fsync overhead.

**Fix:** Expose `begin()`/`commit()` context manager for batching.

---

### PERF-16: Content cache uses FIFO eviction, not LRU (P3)

**File:** `src/mergeguard/core/engine.py:190, 197-216`

Cache eviction uses `pop(next(iter(...)))` (FIFO). Frequently accessed files can be evicted while rarely-used entries persist. Also, 500 entries x 500KB = up to 250MB with no byte-size limit.

**Fix:** Use `functools.lru_cache` or `OrderedDict` with LRU semantics. Add byte-size tracking.

---

### PERF-17: `file_paths` property materializes new set on every call (P3)

**File:** `src/mergeguard/models.py:156-158`

`PRInfo.file_paths` creates a new `set[str]` every time. Called in loops during file overlap computation.

**Fix:** Use `functools.cached_property`.

---

### PERF-18: Recomputed BFS per other PR in transitive detection (P3)

**File:** `src/mergeguard/core/engine.py:833-844`

In Direction B of `_detect_transitive_conflicts()`, `graph.get_dependents(cf.path)` triggers a BFS for every file of every PR. Combined with PERF-05 (list.pop(0)), this compounds significantly.

**Fix:** Pre-compute dependents for all relevant files once and cache in a dict.

---

## 4. Quality

### QUAL-01: Version string mismatch — 0.1.0 / 0.2.0 / 0.5.0 (P1)

**Files:** `src/mergeguard/__init__.py:5` (`"0.1.0"`), `pyproject.toml:3` (`"0.2.0"`), `src/mergeguard/server/webhook.py:355` (`"0.5.0"`)

Three different versions across the codebase. Confuses users, logs, and debugging.

**Fix:** Single source of truth. Use `importlib.metadata.version("mergeguard")` in `__init__.py` and import from there.

---

### QUAL-02: Naive vs timezone-aware datetimes mixed (P1)

**Files:** `src/mergeguard/models.py:256`, `src/mergeguard/output/blast_radius.py:174`, `src/mergeguard/core/policy.py:198, 223`

Four call sites use `datetime.now(tz=None)` producing naive datetimes. Other parts correctly use `datetime.now(UTC)`. Comparing aware and naive datetimes raises `TypeError` at runtime.

**Fix:** Replace all `datetime.now(tz=None)` with `datetime.now(UTC)`.

---

### QUAL-03: Pervasive `Any` typing in webhook handlers (P2)

**File:** `src/mergeguard/server/webhook.py:50, 76-78, 100-102`

Six function parameters typed as `Any` (`client: Any`, `report: Any`, `cfg: Any`, `engine: Any`). Defeats type checking for the most security-sensitive module.

**Fix:** Use actual types: `SCMClient`, `ConflictReport`, `MergeGuardConfig`, `MergeGuardEngine`.

---

### QUAL-04: `FieldExtractor = Any` instead of Callable (P2)

**File:** `src/mergeguard/core/policy.py:32`

Comment says `Callable[[ConflictReport], Any]` but the actual type is `Any`.

**Fix:** `FieldExtractor = Callable[[ConflictReport], Any]`

---

### QUAL-05: Broad `except Exception` handlers — 25+ instances (P2)

**Files:** Throughout — `engine.py` (5), `webhook.py` (4), `ast_parser.py` (4), `cli.py` (2), `llm_analyzer.py` (2), `policy.py`, `queue.py`, `sarif.py`, `cache.py`, `github_client.py`, `bitbucket_client.py`, `codeowners.py`

Many silently swallow errors and continue with fallback behavior. In `llm_analyzer.py:292, 387`, `except (json.JSONDecodeError, Exception)` is redundant — `Exception` is the superclass.

**Fix:** Catch specific exceptions. Log at `WARNING` minimum when using broad catches.

---

### QUAL-06: No httpx/SQLite context managers (P2)

**Files:** `src/mergeguard/integrations/github_client.py:56`, `gitlab_client.py:47`, `bitbucket_client.py:49`, `src/mergeguard/storage/decisions_log.py:117`, `src/mergeguard/storage/metrics_store.py:182`

Both SCM clients and storage classes create resources in `__init__` with no `__enter__`/`__exit__`. Callers must manually manage cleanup, and exceptions can leak connections/handles.

**Fix:** Implement context manager protocol on all resource-owning classes.

---

### QUAL-07: Missing `ConflictType.SECRET` in fix templates (P2)

**File:** `src/mergeguard/core/fix_templates.py:98-106`

The `_GENERATORS` dict maps conflict types to fix suggestion generators, but `SECRET` is missing. Secret findings never get remediation guidance — `generate_fix_suggestion()` returns `None` silently.

**Fix:** Add a `_secret_suggestion` generator recommending credential rotation and env vars.

---

### QUAL-08: Bitbucket `patch=None` silently disables symbol-level analysis (P2)

**File:** `src/mergeguard/integrations/bitbucket_client.py:410`

Bitbucket's diffstat API doesn't return patch content. `ChangedFile.patch` is always `None`, so diff parsing, secret scanning, and symbol detection produce no results. No warning is logged.

**Fix:** Log a warning. Fetch actual diff content via Bitbucket's diff endpoint.

---

### QUAL-09: Confidence score can exceed 1.0 in attribution (P2)

**File:** `src/mergeguard/analysis/attribution.py:43-75`

Additive scoring: title(0.6) + description(0.4) + marker(0.5) + branch(0.3) + label(0.7) = max 2.5. Conceptually wrong if ever exposed.

**Fix:** Cap at 1.0 with `confidence = min(confidence, 1.0)`, or rename to `score`.

---

### QUAL-10: `queue_depth` metric is a Counter, not a Gauge (P2)

**File:** `src/mergeguard/server/metrics.py:63`

Named `queue_depth` but implemented as a monotonically increasing counter. Produces misleading metrics that never decrease.

**Fix:** Use a Gauge that increments on enqueue and decrements on dequeue, or rename to `total_enqueued`.

---

### QUAL-11: `handler: object` instead of proper Callable in queue (P3)

**File:** `src/mergeguard/server/queue.py:46`

Comment says `callable(WebhookEvent) -> awaitable` but the type is `object`. No type safety on `await self._handler(event)`.

**Fix:** `Callable[[WebhookEvent], Awaitable[None]]` or a `Protocol`.

---

### QUAL-12: Private attribute access across module boundaries (P3)

**Files:** `src/mergeguard/core/engine.py:680`, `src/mergeguard/analysis/symbol_index.py:143, 146`

Both modules reach into `DependencyGraph._forward` and `DependencyGraph._symbol_forward` directly.

**Fix:** Add public accessors to `DependencyGraph`.

---

### QUAL-13: Prometheus histogram has no buckets (P3)

**File:** `src/mergeguard/server/metrics.py:29-50`

`_Histogram` only tracks count and sum — no buckets or quantiles. Renders as "summary" type but can only compute averages.

**Fix:** Add standard histogram buckets (1s, 5s, 10s, 30s, 60s, 120s, 300s).

---

## 5. Improvement

### IMP-01: MCP server hardcodes GitHub — ignores GitLab/Bitbucket (P1)

**Files:** `src/mergeguard/mcp/server.py:82, 170`

`check_conflicts` and `get_risk_score` always create a `GitHubClient`. No `platform` parameter. GitLab/Bitbucket repos will fail.

**Fix:** Add `platform` parameter and client factory matching the webhook server pattern.

---

### IMP-02: No `--exit-code` option for CI usage (P1)

**File:** `src/mergeguard/cli.py`

No CLI command exits with non-zero code when conflicts are found. Impossible to use as a CI gate without parsing JSON output.

**Fix:** Add `--exit-code` / `--fail-on-critical` that returns exit code 1 on critical conflicts.

---

### IMP-03: Config validation doesn't warn on unknown keys (P2)

**File:** `src/mergeguard/config.py`

Pydantic V2 ignores unknown fields by default. A typo like `rissk_threshold: 50` is silently ignored.

**Fix:** Use `model_config = ConfigDict(extra="forbid")` or `extra="warn"`.

---

### IMP-04: No structured logging (P2)

**Files:** All source files

All logging uses string formatting. For production, structured JSON logging with fields like `repo`, `pr_number`, `duration_ms` would enable proper log aggregation.

**Fix:** Consider `structlog` or JSON logging configuration.

---

### IMP-05: No request correlation ID for webhook tracing (P2)

**Files:** `src/mergeguard/server/webhook.py`, `src/mergeguard/server/queue.py`

No correlation ID flows through queue, analysis, and comment posting. Debugging requires correlating log lines by timestamp.

**Fix:** Generate a UUID at webhook receipt and propagate through the pipeline.

---

### IMP-06: `scan-secrets` command does full analysis — wasted work (P2)

**File:** `src/mergeguard/cli.py:988-989`

Calls `engine.analyze_pr()` which fetches all open PRs, does pairwise comparison, etc. Secret scanning only needs the target PR's diff.

**Fix:** Add a lightweight scan-only path that skips conflict detection.

---

### IMP-07: SQLite without WAL mode (P2)

**Files:** `src/mergeguard/storage/metrics_store.py`, `src/mergeguard/storage/decisions_log.py`

Default rollback journal mode causes lock contention under concurrent webhook analysis.

**Fix:** Add `PRAGMA journal_mode=WAL` at connection time.

---

### IMP-08: No volume mount for cache/DB in docker-compose (P2)

**File:** `docker-compose.yml`

`.mergeguard-cache/` (containing SQLite databases) is ephemeral. Every container restart loses all history and metrics.

**Fix:** Add a volume mount.

---

### IMP-09: No `--quiet` / `-q` flag for CI (P3)

**File:** `src/mergeguard/cli.py`

The CLI has `--verbose` but no quiet mode. Rich spinner output clutters CI logs.

**Fix:** Add `--quiet` that suppresses everything except formatted output.

---

### IMP-10: No liveness vs readiness distinction for health probes (P3)

**File:** `src/mergeguard/server/webhook.py:360-370`

Single `/health` endpoint serves both. No readiness check during startup or shutdown.

**Fix:** Separate `/healthz` (liveness) and `/readyz` (readiness).

---

### IMP-11: `git_local.py` doesn't handle Bitbucket or self-hosted instances (P3)

**File:** `src/mergeguard/integrations/git_local.py:53-62`

`detect_platform` and `get_repo_full_name` only handle `github.com` and `gitlab.com` URLs.

**Fix:** Add `bitbucket.org` support and a generic fallback.

---

## 6. Testing

### TEST-01: 14 source modules with no dedicated test file (P2)

Missing test coverage for:

| Module | Lines | Risk |
|--------|-------|------|
| `output/notifications.py` | 329 | Untested user-facing Slack/Teams formatting |
| `output/html_report.py` | — | HTML generation |
| `output/dashboard_html.py` | — | Dashboard HTML |
| `output/metrics_html.py` | — | Metrics HTML |
| `output/badge.py` | — | Badge SVG |
| `output/terminal.py` | — | Terminal output |
| `mcp/server.py` | — | MCP integration |
| `server/metrics.py` | — | Buggy `queue_depth` Counter |
| `integrations/llm_analyzer.py` | 404 | Complex parsing with `Any` types |
| `integrations/bitbucket_client.py` | — | No unit tests; patch=None bug |
| `integrations/git_local.py` | — | Local git operations |
| `core/merge_order.py` | 310 | Merge ordering algorithm |
| `core/fix_templates.py` | — | Fix template generation |
| `core/guardrails.py` | — | Production `assert` statements |

**Fix:** Prioritize `notifications.py`, `llm_analyzer.py`, `bitbucket_client.py`, and `guardrails.py`.

---

## 7. Cleanup

### CLN-01: Rate limit checking duplicated across three SCM clients (P2)

**Files:** `github_client.py`, `gitlab_client.py`, `bitbucket_client.py`

Nearly identical `_check_rate_limit` logic in all three. Also duplicated PR-to-model mapping logic.

**Fix:** Extract `RateLimitMixin` or standalone helper.

---

### CLN-02: Duplicated `_DEFAULT_BRANCHES` constant with diverging values (P2)

**Files:** `src/mergeguard/cli.py:21`, `src/mergeguard/analysis/stacked_prs.py:19`

Defined separately in both files — `cli.py` includes `"HEAD"`, `stacked_prs.py` does not.

**Fix:** Single canonical set in `constants.py`.

---

### CLN-03: `constants.py` is largely dead code (P3)

**File:** `src/mergeguard/constants.py`

`DEFAULT_MAX_OPEN_PRS = 30` vs `MergeGuardConfig.max_open_prs = 200`. Most constants are either duplicated in config model defaults or never referenced.

**Fix:** Audit references and remove dead constants.

---

### CLN-04: Duplicated `MAX_FILE_SIZE` constant (P3)

**Files:** `src/mergeguard/constants.py:21`, `src/mergeguard/core/engine.py:59`

Same value (500,000), different name, no import relationship.

**Fix:** Remove from `engine.py`, import from `constants.py`.

---

### CLN-05: Constants defined in both `constants.py` and `MergeGuardConfig` with different defaults (P3)

**Files:** `src/mergeguard/constants.py:20` (`DEFAULT_MAX_OPEN_PRS = 30`), `src/mergeguard/models.py:515` (`max_open_prs = 200`)

Maintenance hazard — which is the real default?

**Fix:** Remove constants.py values that are superseded by config model defaults.

---

### CLN-06: Unnecessary `getattr(self, "_config", None)` pattern — 5 instances (P3)

**File:** `src/mergeguard/core/engine.py:210, 771, 910, 1110, 1552`

`_config` is always assigned in `__init__`. The defensive `getattr` adds noise and confuses readers.

**Fix:** Use `self._config` directly.

---

### CLN-07: Severity counting duplicated in notification formatters (P3)

**File:** `src/mergeguard/output/notifications.py:47-49, 156-158`

Same dict accumulation pattern copy-pasted in `notify_slack` and `notify_teams`.

**Fix:** Extract `_count_severities()` helper.

---

### CLN-08: `import re` inside function body (P3)

**File:** `src/mergeguard/analysis/similarity.py:89`

Inconsistent with rest of codebase where `re` is imported at module level.

**Fix:** Move to top of file.

---

### CLN-09: `map` CLI command shadows Python builtin (P3)

**File:** `src/mergeguard/cli.py:360`

The function is named `map`, shadowing Python's `map()`.

**Fix:** Rename the function (Click command name stays `map` via decorator).

---

## Recommended Fix Order

### Phase 1: Blockers (P0) — fix before any deployment

| # | Finding | Effort |
|---|---------|--------|
| 1 | SEC-01: Webhook auth bypass | S |
| 2 | REL-01: httpx Client leak | M |

### Phase 2: Production-critical (P1) — fix before production

| # | Finding | Effort |
|---|---------|--------|
| 3 | SEC-02: SSRF via webhook URLs | S |
| 4 | SEC-03: SSRF via base URLs + token leak | M |
| 5 | SEC-04: MCP token exposure | S |
| 6 | SEC-05: Shell injection in entrypoint.sh | M |
| 7 | SEC-06: Docker runs as root | S |
| 8 | REL-02: No retry for GitLab/Bitbucket | M |
| 9 | REL-03: assert in production code | S |
| 10 | REL-04: No circuit breaker | M |
| 11 | REL-05: No graceful shutdown | M |
| 12 | QUAL-01: Version mismatch | S |
| 13 | QUAL-02: Naive datetimes | S |
| 14 | PERF-01: Sync call in async handler | S |
| 15 | PERF-02: Blocking sleep in async context | S |
| 16 | PERF-03: N+1 in MCP tool | M |
| 17 | IMP-01: MCP hardcodes GitHub | M |
| 18 | IMP-02: No CI exit codes | S |

### Phase 3: Post-launch (P2) — fix soon after launch

33 findings — see P2 items above. Prioritize by effort/impact.

### Phase 4: Tech debt (P3) — address incrementally

22 findings — cleanup, naming, minor optimizations.
