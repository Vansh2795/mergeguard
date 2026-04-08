# MergeGuard Benchmark Results

Precision and performance measurements against real open-source repositories.

## Methodology

1. Fetch up to 30 recent open PRs from each repo
2. Run `mergeguard analyze` on each PR
3. Record: conflicts found, risk scores, analysis time, errors
4. Manual labeling (separate pass): classify conflicts as true/false positive

## Results

> **Status:** Awaiting first benchmark run. Run `GITHUB_TOKEN=... python benchmarks/run_benchmarks.py` to generate results.

Results will be published here after the Phase 3 benchmark pass.

## Target Repos

| Repo | Language | Reason |
|------|----------|--------|
| langchain-ai/langchain | Python | Large PR volume, cross-file heavy |
| fastapi/fastapi | Python | Well-structured, clean imports |
| vercel/next.js | TS/JS | Heavy PR activity |
| golang/go | Go | Different import paradigm |

## Acceptance Criteria

- Precision >= 80% (manual labeling)
- Zero crashes
- Analysis < 60s per PR for repos with < 100 open PRs
