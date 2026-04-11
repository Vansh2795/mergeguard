"""Capture PR data from GitHub for offline benchmarks.

Usage:
    GITHUB_TOKEN=ghp_... python benchmarks/capture.py owner/repo [--max-prs N]
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Fix Windows encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mergeguard.config import load_config
from mergeguard.core.engine import MergeGuardEngine
from mergeguard.integrations.github_client import GitHubClient
from mergeguard.models import FileChangeStatus

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def capture_repo(repo, token, max_prs=10):
    """Capture all PR data + file contents + baseline analysis results."""
    client = GitHubClient(token, repo)
    cfg = load_config()
    cfg.secrets.enabled = False
    engine = MergeGuardEngine(config=cfg, client=client)

    try:
        fixture = {
            "repo": repo,
            "captured_at": datetime.now(UTC).isoformat(),
            "prs": [],
            "file_contents": {},
        }

        prs = client.get_open_prs(max_count=max_prs, max_age_days=30)
        print(f"Found {len(prs)} open PRs")

        for pr in prs:
            print(f"\n  Capturing PR #{pr.number}: {pr.title[:50]}...")

            # Get changed files
            files = client.get_pr_files(pr.number)

            # Build PR data dict
            pr_data = {
                "number": pr.number,
                "title": pr.title,
                "author": pr.author,
                "base_branch": pr.base_branch,
                "head_branch": pr.head_branch,
                "head_sha": pr.head_sha,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "labels": pr.labels,
                "description": pr.description or "",
                "is_fork": pr.is_fork,
                "changed_files": [],
            }

            # Capture each file's data and content
            for f in files:
                cf_data = {
                    "path": f.path,
                    "status": f.status.value,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "patch": f.patch,
                }
                if f.previous_path:
                    cf_data["previous_path"] = f.previous_path
                pr_data["changed_files"].append(cf_data)

                # Capture file content at base branch
                if f.status != FileChangeStatus.REMOVED:
                    key_base = f"{pr.base_branch}:{f.path}"
                    if key_base not in fixture["file_contents"]:
                        content = client.get_file_content(f.path, pr.base_branch)
                        if content:
                            fixture["file_contents"][key_base] = content

                    # Also capture at head SHA for new files
                    key_head = f"{pr.head_sha}:{f.path}"
                    if key_head not in fixture["file_contents"]:
                        content_head = client.get_file_content(f.path, pr.head_sha)
                        if content_head:
                            fixture["file_contents"][key_head] = content_head

            # Record baseline: run online analysis
            print("    Running baseline analysis...")
            try:
                report = engine.analyze_pr(pr.number)
                type_counts = {}
                for c in report.conflicts:
                    t = c.conflict_type.value
                    type_counts[t] = type_counts.get(t, 0) + 1
                pr_data["baseline"] = {
                    "conflict_count": len(report.conflicts),
                    "risk_score": round(report.risk_score, 1),
                    "conflict_types": type_counts,
                }
                n = len(report.conflicts)
                print(f"    Baseline: {n} conflicts, risk={report.risk_score:.0f}")
            except Exception as e:
                print(f"    Baseline FAILED: {e}")
                pr_data["baseline"] = None

            fixture["prs"].append(pr_data)

            # Save progress after each PR (resumable)
            _save_fixture(fixture, repo)

        n_prs = len(fixture["prs"])
        n_files = len(fixture["file_contents"])
        print(f"\nCapture complete: {n_prs} PRs, {n_files} file contents")
        return fixture
    finally:
        client.close()


def _save_fixture(fixture, repo):
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    slug = repo.replace("/", "-")
    path = FIXTURES_DIR / f"{slug}.json"
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Capture PR data for offline benchmarks")
    parser.add_argument("repo", help="GitHub repo (owner/repo)")
    parser.add_argument("--max-prs", type=int, default=10, help="Max PRs to capture")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: Set GITHUB_TOKEN environment variable")
        sys.exit(1)

    print(f"Capturing {args.repo} (max {args.max_prs} PRs)...")
    capture_repo(args.repo, token, args.max_prs)


if __name__ == "__main__":
    main()
