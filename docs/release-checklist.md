# MergeGuard v1.0.0 Release Checklist

---

## Pre-Release Verification

- [x] All 695+ tests pass (`uv run pytest -v`)
- [x] No import errors (`uv run python -c "import mergeguard"`)
- [x] CLI commands work (`uv run mergeguard --version`)
- [x] `uv run mergeguard analyze --help` shows all options

---

## Security Readiness

19 critical/high audit findings resolved in V1 (see CHANGELOG 1.0.0). Key hardening:

- Git argument injection protection (`--` separators)
- ReDoS in secret patterns (bounded quantifiers)
- SSRF protection for webhook URLs (connect-time IP validation)
- XSS in SVG badges (XML escaping)
- Markdown injection in PR comments (sanitization)
- LLM prompt injection (XML delimiters around diff content)
- Token leakage via httpx repr (custom Auth classes)
- Bitbucket path traversal (URL encoding)
- SQLite thread safety for webhook server

---

## Performance Readiness

- Content cache with LRU eviction (500 entries max)
- Parallel PR enrichment (ThreadPoolExecutor, 8 workers, 300s timeout)
- O(N) collision map via file-to-PR index
- Analysis cache keyed by `(repo, pr_number, head_sha)`

Benchmarks: <15s for 10 PRs, <45s for 30 PRs, ~92 API calls per analysis.

---

## Code Quality

- 695+ tests (unit + integration + edge cases + concurrency + error recovery)
- 72% coverage with CI enforcement (65% threshold)
- Transitive conflict detection overhauled (59-82% false positive reduction)
- Benchmarked against FastAPI and LangChain with published results

---

## Scope Changes in V1

- Secret scanning demoted to opt-in (`--secrets` flag or `secrets.enabled: true`)
- `scan-secrets` command hidden from default CLI help
- README rewritten for clear value proposition

---

## Documentation

- [x] `docs/testing-strategy.md` test counts updated
- [x] `docs/getting-started.md` installation instructions accurate
- [x] `docs/configuration.md` lists all config options and opt-in secrets
- [x] `README.md` feature list current
- [x] `ROADMAP.md` V1 entry added
- [x] `CHANGELOG.md` V1 section complete

---

## Build & Publish

- [ ] Version in `pyproject.toml` is `1.0.0`
- [ ] `uv build` succeeds
- [ ] Package installs cleanly
- [ ] Entry point works: `mergeguard --version` shows `1.0.0`
- [ ] `uv publish` to PyPI

---

## Post-Release

- [ ] Tag release: `git tag v1.0.0 && git push --tags`
- [ ] Create GitHub release with changelog
- [ ] Verify `pip install py-mergeguard` works from PyPI

---

## Known Limitations (v1.0.0)

- Bitbucket Cloud does not support labels (no-ops gracefully)
- Redis queue backend for webhook server is experimental
- Self-hosted runner deployment not yet documented
- IDE integration (VS Code extension) not yet started
- AI conflict resolution (LLM-powered merge suggestions) not yet started
