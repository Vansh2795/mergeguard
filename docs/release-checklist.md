# MergeGuard v0.5.0 Release Checklist

---

## Pre-Release Verification

- [x] All 256 tests pass (`uv run pytest -v`)
- [x] No import errors (`uv run python -c "import mergeguard"`)
- [x] CLI commands work (`uv run mergeguard --version`)
- [x] `uv run mergeguard analyze --help` shows all options

---

## Security Readiness

38/44 audit issues resolved (all critical, high, and medium). 6 low-impact issues intentionally deferred (see `docs/code-audit.md`).

Key security features in place:

- Atomic cache writes with symlink rejection (`cache.py`)
- Token removed from default HTTP headers (`github_client.py`)
- Specific exception handling — auth/network errors propagate (`github_client.py`)
- CLI input validation: `--pr` uses `IntRange(min=1)`, `--repo` validates `owner/repo` format (`cli.py`)
- YAML fallback parser validates keys against model fields (`config.py`)
- GITHUB_OUTPUT support with restrictive /tmp permissions (`json_report.py`)
- Binary file detection and file size limits (500KB) in engine (`engine.py`)
- Diff size limit (50K lines) prevents memory exhaustion (`diff_parser.py`)
- No secrets in codebase (`.env` files gitignored)
- Dependencies: httpx, click, pydantic, tree-sitter (all well-maintained)

---

## Performance Readiness

Key optimizations in place:

- Content cache with LRU eviction (500 entries max) — eliminates duplicate API calls
- Parallel PR enrichment (ThreadPoolExecutor, 8 workers, 300s timeout)
- O(N) collision map via file-to-PR index (was O(N^2))
- O(1) symbol lookup dicts in conflict detection
- Pre-compiled fnmatch patterns for ignored paths
- Combined tree-sitter parse (symbols + call graph in single pass)
- Jaccard pre-filter before expensive SequenceMatcher
- Single-lock pattern for reduced lock contention
- Analysis cache keyed by `(repo, pr_number, head_sha)` — repeated CI runs are free

Benchmarks: <15s for 10 PRs, <45s for 30 PRs, ~92 API calls per analysis.

---

## Code Quality

- 256 tests (unit + integration + edge cases + concurrency + error recovery)
- All Pydantic V2 models with strict validation
- Logging in all key modules (`engine.py`, `github_client.py`, `conflict.py`, `dependency.py`, `diff_parser.py`)
- Named constants for all scoring parameters (no magic numbers)
- `_enrich_pr` decomposed into focused helpers

---

## Documentation

- [x] `docs/testing-strategy.md` test counts updated
- [x] `docs/code-audit.md` reflects all fixes
- [x] `docs/getting-started.md` installation instructions accurate
- [x] `docs/configuration.md` lists all config options
- [x] `README.md` feature list current

---

## Build & Publish

- [x] Version in `pyproject.toml` is correct (`0.1.0`)
- [x] `uv build` succeeds
- [x] Package installs cleanly: `pip install dist/py_mergeguard-0.1.0-py3-none-any.whl`
- [x] Entry point works: `mergeguard --version` shows `0.1.0`
- [x] `uv publish` to PyPI (published as `py-mergeguard`)

---

## Post-Release

- [x] Tag release: `git tag v0.1.0 && git push --tags`
- [x] Create GitHub release with changelog
- [x] Verify `pip install py-mergeguard` works from PyPI
- [x] Run smoke test against mlflow/mlflow (PR #21273 analyzed successfully)

---

## Known Limitations (v0.5.0)

- Bitbucket Cloud does not support labels (no-ops gracefully)
- Redis queue backend for webhook server is experimental
- Self-hosted runner deployment not yet documented
- IDE integration (VS Code extension) not yet started
- AI conflict resolution (LLM-powered merge suggestions) not yet started
