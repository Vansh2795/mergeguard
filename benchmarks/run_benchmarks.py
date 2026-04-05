"""Benchmark MergeGuard accuracy against real open-source repos.

Usage:
    GITHUB_TOKEN=ghp_... python benchmarks/run_benchmarks.py

Writes results to benchmarks/results/
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mergeguard.config import load_config  # noqa: E402
from mergeguard.core.engine import MergeGuardEngine  # noqa: E402
from mergeguard.integrations.github_client import GitHubClient  # noqa: E402

BENCHMARK_REPOS = [
    "langchain-ai/langchain",
    "fastapi/fastapi",
    "vercel/next.js",
    "golang/go",
]

RESULTS_DIR = Path(__file__).parent / "results"


def run_single_repo(repo: str, token: str) -> dict:
    """Run MergeGuard against a repo and collect results."""
    print(f"\n{'=' * 60}")
    print(f"Benchmarking: {repo}")
    print(f"{'=' * 60}")

    client = GitHubClient(token, repo)
    cfg = load_config()
    cfg.secrets.enabled = False

    try:
        engine = MergeGuardEngine(config=cfg, client=client)

        prs = client.get_open_prs(max_count=50, max_age_days=30)
        print(f"  Found {len(prs)} open PRs")

        results: list[dict] = []
        errors: list[dict] = []
        start = time.monotonic()

        for pr in prs[:30]:
            try:
                pr_start = time.monotonic()
                report = engine.analyze_pr(pr.number)
                pr_elapsed = time.monotonic() - pr_start

                results.append(
                    {
                        "pr_number": pr.number,
                        "pr_title": pr.title,
                        "pr_author": pr.author,
                        "conflicts_found": len(report.conflicts),
                        "risk_score": report.risk_score,
                        "conflict_types": [
                            c.conflict_type.value for c in report.conflicts
                        ],
                        "conflict_severities": [
                            c.severity.value for c in report.conflicts
                        ],
                        "conflict_descriptions": [
                            c.description for c in report.conflicts
                        ],
                        "analysis_ms": int(pr_elapsed * 1000),
                    }
                )
                n = len(report.conflicts)
                print(
                    f"  PR #{pr.number}: {n} conflict(s), "
                    f"risk={report.risk_score:.0f}, {pr_elapsed:.1f}s"
                )

            except Exception as e:
                errors.append({"pr_number": pr.number, "error": str(e)})
                print(f"  PR #{pr.number}: ERROR -- {e}")

        total_elapsed = time.monotonic() - start

        return {
            "repo": repo,
            "timestamp": datetime.now(UTC).isoformat(),
            "prs_analyzed": len(results),
            "prs_errored": len(errors),
            "total_conflicts": sum(r["conflicts_found"] for r in results),
            "total_elapsed_s": round(total_elapsed, 1),
            "avg_analysis_ms": (
                round(sum(r["analysis_ms"] for r in results) / len(results))
                if results
                else 0
            ),
            "results": results,
            "errors": errors,
        }
    finally:
        client.close()


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: Set GITHUB_TOKEN environment variable")
        sys.exit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []
    for repo in BENCHMARK_REPOS:
        try:
            result = run_single_repo(repo, token)
            all_results.append(result)

            date = datetime.now(UTC).strftime("%Y-%m-%d")
            repo_slug = repo.replace("/", "-")
            output_path = RESULTS_DIR / f"{date}-{repo_slug}.json"
            output_path.write_text(json.dumps(result, indent=2))
            print(f"\n  Results saved to {output_path}")

        except Exception as e:
            print(f"\nFATAL ERROR on {repo}: {e}")
            all_results.append({"repo": repo, "error": str(e)})

    print(f"\n{'=' * 60}")
    print("BENCHMARK SUMMARY")
    print(f"{'=' * 60}")
    for r in all_results:
        if "error" in r and "prs_analyzed" not in r:
            print(f"  {r['repo']}: FAILED -- {r['error']}")
        else:
            total = r["total_conflicts"]
            prs = r["prs_analyzed"]
            avg = r["avg_analysis_ms"]
            print(f"  {r['repo']}: {prs} PRs, {total} conflicts, avg {avg}ms/PR")


if __name__ == "__main__":
    main()
