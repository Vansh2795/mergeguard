# MergeGuard V1 Release Design

**Date:** 2026-04-04
**Status:** Approved
**Author:** Vansh Bajaj + Claude
**Approach:** Accuracy First (open-source-first adoption)

---

## Goal

Ship MergeGuard V1 as the only open-source tool that detects cross-PR conflicts proactively — during development, not at merge time. V1 must prove its core detection works accurately on real repos, deliver a frictionless first-run experience, and establish trust through published benchmark results.

## Positioning

**One sentence:** "MergeGuard detects cross-PR conflicts — hard conflicts, interface breaks, behavioral incompatibilities, duplications, transitive chains, and regressions — before they reach your merge queue."

**Competitive niche:** Merge queues (Mergify, Aviator, Trunk) detect conflicts reactively at merge time. AI review tools (CodeRabbit, Qodo, DeepSource) review individual PRs. MergeGuard is the only tool focused on cross-PR conflict detection during development. It works alongside any merge strategy — not a replacement for CI or merge queues, but an early warning system.

**Adoption path:** Open-source-first (MIT). Goal is GitHub stars, community adoption, and contributors. Monetization deferred.

---

## V1 Scope

### V1 IS

- Accurate cross-PR conflict detection (6 types: hard, interface, behavioral, duplication, transitive, regression)
- Proven accuracy via published benchmark results (precision >= 80%)
- Works on GitHub, GitLab, Bitbucket (all properly tested)
- CLI + GitHub Action
- Zero-config first run (auto-detect platform/repo from git remote)
- 75%+ test coverage with CI enforcement gate
- Clean README focused on one value proposition
- Webhook server for real-time detection
- Policy engine, DORA metrics, blast radius, MCP server (shipped and documented but not front-page features)

### V1 IS NOT

- Secret scanning (hidden behind explicit `--secrets` flag, removed from default pipeline and marketing)
- AI-powered fix suggestions (deferred to V1.1)
- IDE extension (deferred)
- OAuth app / SaaS hosting (deferred)
- Interactive PR chat (deferred)
- Azure DevOps / Gitea support (deferred)
- Cross-repo conflict detection (deferred)

### V1 Success Metrics

- Precision >= 80% on benchmark suite (no more than 1 in 5 flagged conflicts is noise)
- Zero crashes on any benchmark repo
- Analysis completes within 60s for repos with < 100 open PRs
- 75%+ test coverage enforced in CI
- README-to-first-result in < 5 minutes

### Version

`1.0.0` with classifier `Development Status :: 4 - Beta`. Upgradeable to `Production/Stable` after community validation.

---

## Phase 1: Detection Fixes

Fix parser and detection logic bugs that directly impact accuracy. Must complete before benchmarks are meaningful.

### Parser Fixes

| Bug | File | Impact | Fix |
|-----|------|--------|-----|
| `.tsx` detected as TypeScript | `analysis/ast_parser.py:101-106` | Wrong parse tree for React components | Sort extensions by length (longest first) before matching, or use `os.path.splitext()` |
| Multi-line Python imports drop symbols | `analysis/dependency.py:154,210-214` | Cross-file detection blind to `from X import (\n A, B)` | When opening paren detected, continue reading until closing paren, collect all names |
| Go import regex matches any quoted string | `analysis/dependency.py:163` | False positive symbol dependencies | Scope regex to `import (...)` blocks and `import "..."` statements only |
| `fnmatch` doesn't support `**` globs | `analysis/codeowners.py:148-158` | CODEOWNERS recursive patterns silently fail | Use `pathlib.PurePosixPath.match()` which handles `**` |
| Unbounded AST recursion | `analysis/ast_parser.py:152-264` | Crashes on deeply nested/generated code | Catch `RecursionError` in `_walk_tree` and siblings, return empty results |

### Severity Calibration

After parser fixes and initial benchmark runs, tune conflict severity based on false positive data:
- DUPLICATION between similarly-named functions in different modules: likely demote to INFO
- BEHAVIORAL where both PRs only add code (no removals): likely demote to INFO
- Specific thresholds determined by benchmark Phase 3 results

---

## Phase 2: Hardening & Test Coverage

Runs in parallel with Phase 1.

### Test Coverage Targets

| Category | Current | V1 Target | Approach |
|----------|---------|-----------|----------|
| `engine.analyze_pr()` integration | 0% | 1 full end-to-end test | Mock SCM client, verify full pipeline |
| Cross-file conflict detection | 0% | 3-5 cases | Python, TypeScript, Go import scenarios |
| Bitbucket client HTTP methods | ~10% | Parity with GitLab | respx mocks for all 7 public methods |
| Output formatters (6 modules) | 0% | Smoke tests | Each produces valid output, covers XSS |
| `rate_limit.py` | 0% | Core paths | Backoff calculation, bad headers, thresholds |
| `decisions_log.py` | 0% | CRUD ops | Record, query, find_regressions with real SQLite |
| Protocol compliance | Missing Bitbucket | All 3 clients | Add BitbucketClient to existing test |

### CI Quality Gates

Add to `pyproject.toml`:
```toml
[tool.coverage.run]
source = ["mergeguard"]

[tool.coverage.report]
fail_under = 75
```

### Crash Fixes

| Bug | File | Fix |
|-----|------|-----|
| SQLite `check_same_thread` | `storage/decisions_log.py:19-24` | `check_same_thread=False` + `threading.Lock` around writes |
| `int()` on non-numeric rate header | `integrations/rate_limit.py:29` | `try/except ValueError: return` |
| AST recursion limit | `analysis/ast_parser.py:152-264` | `try/except RecursionError` in tree walkers |
| Config retry raises on secondary validation | `config.py:58` | Wrap retry in its own try/except, fall back to defaults |
| GitLab `request_reviewers` replaces reviewers | `integrations/gitlab_client.py:286-289` | Fetch current reviewers first, merge |
| Bitbucket `get_open_prs` doesn't break on age cutoff | `integrations/bitbucket_client.py:96-99` | Add `sort=-updated_on`, change `continue` to `break` |

---

## Phase 3: Benchmark Suite

Depends on Phase 1 (detection must be accurate before measuring).

### Target Repos

| Repo | Language | Selection Reason |
|------|----------|-----------------|
| langchain-ai/langchain | Python | Already in test strategy, large PR volume, cross-file heavy |
| fastapi/fastapi | Python | Well-structured, moderate activity, clean imports |
| microsoft/TypeScript | TypeScript | Large codebase, complex cross-file dependencies |
| vercel/next.js | TS/JS | Monorepo-adjacent, heavy PR activity |
| golang/go | Go | Different language paradigm, import system |

### Methodology

1. For each repo, fetch all open PRs (or recent historical window of 30-50 merged PRs)
2. Run `mergeguard analyze` on each PR
3. Manual labeling: for ~50 PR pairs per repo, classify each conflict as true positive or false positive
4. Record: precision (TP / (TP + FP)), qualitative log of "why did this FP happen"
5. Feed FP causes back into Phase 4 severity tuning

### Deliverables

- `benchmarks/` directory with:
  - `run_benchmarks.py` — repeatable runner script
  - `results/YYYY-MM-DD-<repo>.json` — raw results per repo
  - `BENCHMARKS.md` — published summary with precision numbers, example outputs, performance timings
- README badge linking to benchmark results

### Acceptance Criteria

- Precision >= 80% across all repos
- Zero crashes
- Analysis < 60s for repos with < 100 open PRs

---

## Phase 4: Accuracy Tuning

Depends on Phase 3 results.

- Analyze false positive patterns from benchmark labeling
- Adjust severity thresholds (demote noisy conflict types to INFO)
- Fix any systematic detection bugs surfaced by real-world data
- Re-run benchmarks to verify improvement
- Iterate until precision >= 80%

This is the phase where we learn what we don't know. Budget flexibility here — could be 1 week or 3 weeks depending on what benchmarks reveal.

---

## Phase 5: Scope Reduction

Runs in parallel with any phase.

### Secret Scanning Changes

- Remove `scan-secrets` from default CLI help (move to hidden command group)
- Remove secret scanning from default `analyze` pipeline
- Remove `secrets` section from `.mergeguard.yml.example`
- Remove secret scanning from README feature list
- Keep `--secrets` flag working for explicit opt-in
- Keep all secret scanning code in tree (not deleted)

### CLI Surface Trim

Default `mergeguard --help` shows:
- `analyze` — Analyze a PR for cross-PR conflicts
- `map` — Show collision map of all open PRs
- `suggest-order` — Suggest optimal merge order
- `watch` — Continuously monitor for conflicts
- `serve` — Start webhook server
- `init` — Interactive setup

Secondary commands (available but not in default help or in a separate group):
- `dashboard`, `blast-radius`, `policy-check`, `metrics`, `history`, `analyze-multi`, `scan-secrets`

---

## Phase 6: First-Run Polish

Depends on Phase 4 (need real benchmark numbers and proven accuracy).

### README Rewrite

Structure:
1. One-liner value prop
2. 30-second demo GIF showing a real conflict found on a benchmark repo
3. Install + first command (3 lines of shell)
4. "What it detects" — 6 conflict types, one sentence each
5. Example output (real terminal screenshot)
6. GitHub Action setup (5 lines of YAML)
7. Benchmark results badge + link
8. Comparison table: MergeGuard vs merge queues vs code review tools
9. Configuration link to docs
10. Contributing link

What gets cut from README: secret scanning, DORA metrics details, policy engine details, blast radius details, MCP server details. All stay in docs/ — just not on the front page.

### Demo Recording

Run MergeGuard against one of the benchmark repos, capture terminal output showing a genuine conflict detected. Convert to GIF for README. This is the single most important README element.

### Comparison Table for README

| | MergeGuard | Merge Queues (Mergify, Trunk) | AI Review (CodeRabbit, Qodo) |
|---|---|---|---|
| Detects cross-PR conflicts | During development | At merge time | No |
| Requires workflow change | No | Yes (adopt queue) | No |
| Open source | MIT | Commercial | Commercial |
| Multi-platform | GitHub + GitLab + Bitbucket | GitHub only (mostly) | GitHub (mostly) |
| Works with existing CI | Yes | Replaces merge flow | Yes |

---

## Phase 7: Release

Depends on all above.

- Version bump to `1.0.0`
- Update classifier to `Development Status :: 4 - Beta`
- CHANGELOG entry for V1
- Git tag `v1.0`
- Publish to PyPI
- Update GitHub Action to `@v1`
- GitHub Release with summary of what V1 includes
- Consider: HN/Reddit/Twitter launch post linking to benchmark results

---

## Phase Dependencies

```
Phase 1 (Detection fixes) ──────────┐
                                     ├──> Phase 3 (Benchmarks) ──> Phase 4 (Tuning) ──> Phase 6 (Polish) ──> Phase 7 (Release)
Phase 2 (Hardening) ────────────────┘                                                        ^
                                                                                              |
Phase 5 (Scope reduction) ──────────────────────────────────────────────────────────────────────┘
```

Phases 1 & 2 run in parallel.
Phase 5 runs in parallel with everything.
Phases 3 -> 4 -> 6 -> 7 are sequential.

---

## What's Deferred to V1.1+

| Feature | Why Deferred | When |
|---------|-------------|------|
| AI fix suggestions | Core detection must be proven first | V1.1 |
| IDE extension (VS Code) | Adoption via CLI/GH Action first | V1.2 |
| OAuth GitHub/GitLab App | PAT tokens work fine for open source users | V1.2 |
| Interactive PR chat | Nice-to-have, not core value | V1.2 |
| SaaS hosted offering | Requires infrastructure investment | V2 |
| Azure DevOps / Gitea | Smaller user base, not launch-critical | V1.1 |
| Cross-repo conflicts | Complex, needs monorepo story first | V2 |
| Enhanced secret scanning | Can't compete with GitGuardian; not our niche | Unlikely |

---

## Competitive Context

MergeGuard's V1 market position:

**Only tool that:** Detects cross-PR conflicts proactively during development, not at merge time.

**Works alongside:** Any merge strategy — GitHub merge queue, Mergify, manual merges, GitLab merge trains. Not a replacement, an early warning system.

**Open source advantage:** MIT licensed. Every competitor in this space (Mergify, Aviator, Trunk, Graphite) is commercial. CodeQL and GitLab merge trains are free but platform-locked.

**Multi-platform advantage:** GitHub + GitLab + Bitbucket from day one. Most competitors are GitHub-only.
