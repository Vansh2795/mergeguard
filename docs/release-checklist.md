# MergeGuard v0.1.0 Release Checklist

---

## Pre-Release Verification

- [ ] All 214 tests pass (`uv run pytest -v`)
- [ ] No import errors (`uv run python -c "import mergeguard"`)
- [ ] CLI commands work (`uv run mergeguard --version`)
- [ ] `uv run mergeguard analyze --help` shows all options

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

- 214 tests (unit + integration + edge cases + concurrency + error recovery)
- All Pydantic V2 models with strict validation
- Logging in all key modules (`engine.py`, `github_client.py`, `conflict.py`, `dependency.py`, `diff_parser.py`)
- Named constants for all scoring parameters (no magic numbers)
- `_enrich_pr` decomposed into focused helpers

---

## Documentation

- [ ] `docs/testing-strategy.md` test counts updated
- [ ] `docs/code-audit.md` reflects all fixes
- [ ] `docs/getting-started.md` installation instructions accurate
- [ ] `docs/configuration.md` lists all config options
- [ ] `README.md` feature list current

---

## Build & Publish

- [ ] Version in `pyproject.toml` is correct (`0.1.0`)
- [ ] `uv build` succeeds
- [ ] Package installs cleanly: `pip install dist/mergeguard-0.1.0-py3-none-any.whl`
- [ ] Entry point works: `mergeguard --version` shows `0.1.0`
- [ ] `uv publish` to PyPI (requires PyPI token)

---

## Post-Release

- [ ] Tag release: `git tag v0.1.0 && git push --tags`
- [ ] Create GitHub release with changelog
- [ ] Verify `pip install mergeguard` works from PyPI
- [ ] Run smoke test against a public repo (e.g., `langchain-ai/langchain`)

---

## Known Limitations (v0.1.0)

- Transitive conflict detection not implemented (Gap #12)
- `--pr` auto-detection from current branch not implemented (Gap #15)
- GitLab support is stub-only (`NotImplementedError`)
- MCP server tools return `"not_implemented"`
- React dashboard not started (Phase 3 Weeks 15-16)
- No Docker image yet
- 6 deferred low-impact audit issues (S-7, S-9, P-8, P-10, Q-6, Q-7)
