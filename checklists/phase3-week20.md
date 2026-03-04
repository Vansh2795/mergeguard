# Phase 3 — Week 20: Performance Optimization + V2 Launch

## Goals
- Optimize performance and launch V2

## Daily Tasks

### Day 1-2: Incremental Analysis
- [x] Cache PR data and only re-analyze updated PRs
- [x] Use PR updated_at timestamp as cache key
- [x] Implement cache invalidation strategy
- [ ] Verify cache hit rates in CI

### Day 3-4: Parallel Processing
- [x] Parallel AST parsing with concurrent.futures
- [x] Parallel file content fetching
- [ ] Pre-filter: skip PRs that can't conflict (different directories)
- [x] Smart file content fetching (only overlapping files)
- [x] Benchmark: target < 15s for 10 PRs, < 45s for 30 PRs

### Day 5: V2 Launch
- [ ] Update version to 2.0.0
- [ ] Update all documentation
- [ ] Performance benchmarks in README
- [ ] Publish to PyPI
- [ ] Update GitHub Action
- [ ] Write V2 announcement post
- [ ] Update dashboard deployment

## Deliverables
- [x] Incremental analysis with caching
- [x] Parallel processing for AST and API calls
- [ ] V2 with guardrails, dashboard, MCP, GitLab support

## Acceptance Criteria
- [x] Analysis time < 15s for 10 open PRs
- [x] Analysis time < 45s for 30 open PRs
- [ ] Memory usage < 256 MB
- [ ] Docker image < 150 MB
- [ ] All V2 features working end-to-end
- [ ] V2 launched

> **Note:** Parallel enrichment (ThreadPoolExecutor, 8 workers) and content cache (`_content_cache`) are implemented in engine.py. `AnalysisCache` is now wired into the engine (Gap #14 fixed) — keyed by `(repo, pr_number, head_sha)`, cache hit skips all API calls.
