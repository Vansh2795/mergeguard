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

        # Fetch ALL open PRs (engine compares target against all of them)
        all_prs = client.get_open_prs(max_count=200, max_age_days=30)
        print(f"Found {len(all_prs)} open PRs (will baseline {min(max_prs, len(all_prs))})")

        # Pass 1: Capture PR metadata and changed files for ALL PRs
        print("\n--- Pass 1: Capturing PR metadata and file lists ---")
        for pr in all_prs:
            print(f"  PR #{pr.number}: {pr.title[:50]}...")
            files = client.get_pr_files(pr.number)

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

            fixture["prs"].append(pr_data)
        _save_fixture(fixture, repo)

        # Pass 2: Capture file contents for ALL files across ALL PRs
        # The engine needs content for every PR's files (not just the target)
        print(f"\n--- Pass 2: Capturing file contents ---")
        content_keys: set[tuple[str, str]] = set()
        for pr_data in fixture["prs"]:
            base = pr_data["base_branch"]
            head = pr_data["head_sha"]
            for f in pr_data["changed_files"]:
                if f["status"] != "removed":
                    content_keys.add((f["path"], base))
                    content_keys.add((f["path"], head))

        print(f"  {len(content_keys)} unique (path, ref) pairs to fetch")
        fetched = 0
        for path, ref in sorted(content_keys):
            key = f"{ref}:{path}"
            if key in fixture["file_contents"]:
                continue
            try:
                content = client.get_file_content(path, ref)
                if content:
                    fixture["file_contents"][key] = content
                    fetched += 1
            except Exception:
                pass  # Binary files, missing files — skip
            if fetched % 50 == 0 and fetched > 0:
                print(f"    Fetched {fetched} files...")
                _save_fixture(fixture, repo)
        print(f"  Fetched {fetched} file contents")
        _save_fixture(fixture, repo)

        # Pass 3: Run baseline online analysis for first max_prs PRs
        print(f"\n--- Pass 3: Recording baseline analysis (first {max_prs}) ---")
        for pr_data in fixture["prs"][:max_prs]:
            pr_num = pr_data["number"]
            print(f"  PR #{pr_num}: analyzing...")
            try:
                report = engine.analyze_pr(pr_num)
                type_counts: dict[str, int] = {}
                for c in report.conflicts:
                    t = c.conflict_type.value
                    type_counts[t] = type_counts.get(t, 0) + 1
                pr_data["baseline"] = {
                    "conflict_count": len(report.conflicts),
                    "risk_score": round(report.risk_score, 1),
                    "conflict_types": type_counts,
                }
                n = len(report.conflicts)
                print(f"    {n} conflicts, risk={report.risk_score:.0f}")
            except Exception as e:
                print(f"    FAILED: {e}")
                pr_data["baseline"] = None
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
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")


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
