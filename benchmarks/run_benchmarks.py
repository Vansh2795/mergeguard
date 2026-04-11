"""Benchmark MergeGuard accuracy against real open-source repos.

Usage:
    GITHUB_TOKEN=ghp_... python benchmarks/run_benchmarks.py
    python benchmarks/run_benchmarks.py --offline
    python benchmarks/run_benchmarks.py --offline --verify-baseline

Writes results to benchmarks/results/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Fix Windows console encoding for repos with emoji in PR titles
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

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

# Max PRs per repo — keep low to avoid rate limits with free tokens
MAX_PRS_PER_REPO = int(os.environ.get("BENCH_MAX_PRS", "10"))

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

        prs = client.get_open_prs(max_count=MAX_PRS_PER_REPO, max_age_days=30)
        print(f"  Found {len(prs)} open PRs (analyzing up to {MAX_PRS_PER_REPO})")

        results: list[dict] = []
        errors: list[dict] = []
        start = time.monotonic()

        for pr in prs[:MAX_PRS_PER_REPO]:
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


def run_online() -> None:
    """Run benchmarks against live GitHub repos. Requires GITHUB_TOKEN."""
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


def run_offline(verify: bool = False) -> None:
    """Run benchmarks from captured fixtures. Zero API calls."""
    from file_client import FileBasedSCMClient  # noqa: PLC0415

    fixtures_dir = Path(__file__).parent / "fixtures"
    if not fixtures_dir.exists():
        print("ERROR: No fixtures found. Run capture.py first.")
        sys.exit(1)

    fixture_files = sorted(fixtures_dir.glob("*.json"))
    if not fixture_files:
        print("ERROR: No fixture files in benchmarks/fixtures/")
        sys.exit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []
    baseline_mismatches: list[str] = []

    for fixture_path in fixture_files:
        with open(fixture_path, encoding="utf-8") as f:
            fixture = json.load(f)

        repo = fixture["repo"]
        print(f"\n{'=' * 60}")
        print(f"Offline Benchmark: {repo}")
        print(f"{'=' * 60}")
        print(f"Fixture: {fixture_path.name} ({len(fixture['prs'])} PRs)")

        client = FileBasedSCMClient(fixture)
        cfg = load_config()
        cfg.secrets.enabled = False
        engine = MergeGuardEngine(config=cfg, client=client)

        results: list[dict] = []
        for pr_data in fixture["prs"]:
            pr_num = pr_data["number"]
            try:
                start = time.monotonic()
                report = engine.analyze_pr(pr_num)
                elapsed = time.monotonic() - start

                n = len(report.conflicts)
                types: dict[str, int] = {}
                for c in report.conflicts:
                    types[c.conflict_type.value] = types.get(c.conflict_type.value, 0) + 1

                risk = report.risk_score
                print(f"  PR #{pr_num}: {n} conflicts, risk={risk:.0f}, {elapsed:.1f}s")
                print(f"    Types: {types}")

                results.append(
                    {
                        "pr_number": pr_num,
                        "conflicts_found": n,
                        "risk_score": report.risk_score,
                        "conflict_types": types,
                        "analysis_ms": int(elapsed * 1000),
                    }
                )

                # Verify against baseline if requested
                if verify and pr_data.get("baseline"):
                    baseline = pr_data["baseline"]
                    if n != baseline["conflict_count"]:
                        msg = f"PR #{pr_num}: offline={n} vs baseline={baseline['conflict_count']}"
                        print(f"    MISMATCH: {msg}")
                        baseline_mismatches.append(msg)
                    else:
                        print(f"    BASELINE MATCH: {n} conflicts")

            except Exception as e:
                print(f"  PR #{pr_num}: ERROR -- {e}")

        # Save results for this fixture
        date = datetime.now(UTC).strftime("%Y-%m-%d")
        repo_slug = repo.replace("/", "-")
        output_path = RESULTS_DIR / f"{date}-{repo_slug}-offline.json"
        repo_result = {
            "repo": repo,
            "timestamp": datetime.now(UTC).isoformat(),
            "mode": "offline",
            "fixture": fixture_path.name,
            "prs_analyzed": len(results),
            "total_conflicts": sum(r["conflicts_found"] for r in results),
            "results": results,
        }
        output_path.write_text(json.dumps(repo_result, indent=2))
        print(f"\n  Results saved to {output_path}")

        all_results.append(repo_result)

    # Print summary
    print(f"\n{'=' * 60}")
    print("OFFLINE BENCHMARK SUMMARY")
    print(f"{'=' * 60}")
    for r in all_results:
        total = sum(pr["conflicts_found"] for pr in r["results"])
        print(f"  {r['repo']}: {r['prs_analyzed']} PRs, {total} conflicts")

    if verify:
        print(f"\nBaseline verification: {len(baseline_mismatches)} mismatches")
        for m in baseline_mismatches:
            print(f"  {m}")
        if not baseline_mismatches:
            print("  All PRs match baseline!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MergeGuard benchmark runner",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run from captured fixtures (no API calls)",
    )
    parser.add_argument(
        "--verify-baseline",
        action="store_true",
        help="Compare results against captured baselines (requires --offline)",
    )
    args = parser.parse_args()

    if args.offline:
        run_offline(verify=args.verify_baseline)
    else:
        run_online()


if __name__ == "__main__":
    main()
