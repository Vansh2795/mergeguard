# MergeGuard Benchmark Results

Accuracy and performance measurements against real open-source repositories using the offline benchmark system.

## Methodology

1. **Capture**: Fetch all open PRs, changed files, and file contents from each repo via GitHub API (one-time)
2. **Replay**: Run `mergeguard analyze` offline using `FileBasedSCMClient` — zero API calls, identical engine behavior
3. **Verify**: Baseline comparison confirms offline results match online analysis exactly

## Results — 3 Repos, 193 PRs, 0 Crashes

### Summary

| Repo | Language | PRs | Conflict Rate | Total Conflicts | Avg/PR | Crashes |
|------|----------|-----|--------------|-----------------|--------|---------|
| [fastapi/fastapi](https://github.com/fastapi/fastapi) | Python | 70 | 78% | 1,690 | 30.7 | 0 |
| [golang/go](https://github.com/golang/go) | Go | 63 | 15% | 26 | 2.6 | 0 |
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | Python | 60 | 93% | 598 | 10.7 | 0 |
| **Total** | | **193** | | **2,314** | | **0** |

### Conflict Type Breakdown

| Repo | Hard | Behavioral | Transitive | Interface | Duplication |
|------|------|-----------|-----------|-----------|-------------|
| fastapi/fastapi | 320 (18%) | 832 (49%) | 536 (31%) | 0 | 2 |
| golang/go | 12 (46%) | 12 (46%) | 0 | 0 | 2 (7%) |
| langchain-ai/langchain | 120 (20%) | 72 (12%) | 406 (67%) | 0 | 0 |

### Performance

| Repo | Avg | P90 | Max |
|------|-----|-----|-----|
| fastapi/fastapi | 3.0s | 8.9s | 53.5s |
| golang/go | 0.2s | 0.2s | 3.7s |
| langchain-ai/langchain | 1.4s | 2.6s | 23.2s |

### Baseline Verification

| Repo | PRs Verified | Result |
|------|-------------|--------|
| fastapi/fastapi | 3 | 3/3 match |
| langchain-ai/langchain | 5 | 5/5 match |
| **Total** | **8** | **8/8 match (100%)** |

Offline analysis produces identical results to online API-based analysis.

## Analysis by Repo

### FastAPI (Python web framework)

- **78% conflict rate** — tightly-coupled single-package architecture where many PRs touch shared modules (`routing.py`, `dependencies/utils.py`)
- Balanced type mix: behavioral (49%), transitive (31%), hard (18%)
- Transitive cap working correctly — no explosion despite deep import graph
- Top conflicting PR: #15097 with 94 conflicts (large routing refactor touching many dependents)

### Go Standard Library

- **15% conflict rate** — Go's package isolation keeps PRs independent
- Only hard (46%) and behavioral (46%) conflicts — zero transitive (packages don't share imports)
- Fastest analysis: most PRs complete in <200ms
- Demonstrates MergeGuard correctly stays quiet when PRs don't overlap

### LangChain (Python AI/LLM framework)

- **93% conflict rate** — monorepo with many partner packages importing shared core modules
- Transitive-heavy (67%) — reflects deep dependency chains across `libs/core`, `libs/langchain`, and partner packages
- Hard conflicts (20%) concentrated in shared utility modules
- Top conflicting PR: #34514 with 40 conflicts

### Next.js (TypeScript/Rust monorepo)

> **Status**: Benchmark capture complete (200 PRs, 3,226 files). Offline analysis in progress — results pending due to large monorepo PRs (turbopack) requiring extended analysis time. Preliminary data shows 15,822 conflicts with interface detection dominant (14,400) — this highlights a V1.1 tuning opportunity for TypeScript re-exports.

## Transitive Accuracy Improvements

Compared to pre-V1 benchmarks on FastAPI:

| PR | Before Fixes | After Fixes | Reduction |
|----|-------------|-------------|-----------|
| #15307 | 46 conflicts | 19 conflicts | -59% |
| #15215 | 66 conflicts | 12 conflicts | -82% |

Fixes: module form trimming, BFS depth=1, symbol-level evidence, aggregation, global cap.

## Running Benchmarks

### Capture fixtures (one-time, needs GitHub token)
```bash
GITHUB_TOKEN=ghp_... python benchmarks/capture.py owner/repo [--max-prs N]
```

### Run offline (no token needed, reproducible)
```bash
python benchmarks/run_benchmarks.py --offline
```

### Verify offline matches online
```bash
python benchmarks/run_benchmarks.py --offline --verify-baseline
```
