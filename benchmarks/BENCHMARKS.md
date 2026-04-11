# MergeGuard Benchmark Results

Accuracy and performance measurements against real open-source repositories using the offline benchmark system.

## Methodology

1. **Capture**: Fetch all open PRs, changed files, and file contents from each repo via GitHub API (one-time)
2. **Replay**: Run `mergeguard analyze` offline using `FileBasedSCMClient` — zero API calls, identical results
3. **Verify**: Baseline comparison confirms offline results match online (0 mismatches on FastAPI)

## Results (April 2026)

### Summary

| Repo | Language | PRs | With Conflicts | Total Conflicts | Avg per PR | Zero Crashes |
|------|----------|-----|---------------|-----------------|------------|-------------|
| fastapi/fastapi | Python | 70 | 55 (79%) | 1,690 | 30.7 | Yes |
| golang/go | Go | 63 | 10 (16%) | 26 | 2.6 | Yes |
| vercel/next.js | TS/Rust | 200 | 132 (66%) | 15,822 | 119.9 | Yes |

### Conflict Types

| Repo | Hard | Behavioral | Interface | Transitive | Duplication |
|------|------|-----------|-----------|-----------|-------------|
| fastapi/fastapi | 320 | 832 | 0 | 536 | 2 |
| golang/go | 12 | 12 | 0 | 0 | 2 |
| vercel/next.js | 464 | 864 | 14,400 | 0 | 94 |

### Performance

| Repo | Avg | P90 | Max |
|------|-----|-----|-----|
| fastapi/fastapi | 3.9s | 13.0s | 47.7s |
| golang/go | 0.3s | 0.3s | 5.7s |
| vercel/next.js | 90.0s | 112.4s | 5013.7s |

### Analysis

**FastAPI** (Python web framework, 70 PRs):
- High conflict rate (79%) reflects a tightly-coupled single-package architecture where many PRs touch shared modules
- Balanced mix of hard (19%), behavioral (49%), and transitive (32%) conflicts
- Transitive cap working correctly — no explosion despite deep import graph

**Go standard library** (63 PRs):
- Low conflict rate (16%) — Go's package isolation means PRs rarely overlap
- Only hard and behavioral conflicts — zero transitive (independent packages)
- Fastest analysis: most PRs complete in <300ms

**Next.js** (TypeScript/Rust monorepo, 200 PRs):
- 14,400 interface conflicts dominate — this reflects the monorepo structure where many PRs modify exported TypeScript types
- Large PRs (turbopack) cause slow analysis times (max 84 min)
- Interface detection may be over-reporting for TypeScript re-exports — area for V1.1 tuning

### Transitive Accuracy Improvements

Compared to pre-V1 benchmarks on FastAPI:

| Metric | Before Fixes | After Fixes |
|--------|-------------|-------------|
| PR #15307 | 46 conflicts | 19 conflicts (-59%) |
| PR #15215 | 66 conflicts | 12 conflicts (-82%) |

Fixes applied: module form trimming, BFS depth=1, symbol-level evidence for severity, aggregation, global cap.

## Running Benchmarks

### Capture fixtures (one-time, needs GitHub token)
```bash
GITHUB_TOKEN=ghp_... python benchmarks/capture.py fastapi/fastapi
GITHUB_TOKEN=ghp_... python benchmarks/capture.py golang/go
GITHUB_TOKEN=ghp_... python benchmarks/capture.py vercel/next.js
```

### Run offline (no token needed)
```bash
python benchmarks/run_benchmarks.py --offline
```

### Verify offline matches online
```bash
python benchmarks/run_benchmarks.py --offline --verify-baseline
```

Set `BENCH_MAX_PRS=5` to limit PRs per repo during capture.
