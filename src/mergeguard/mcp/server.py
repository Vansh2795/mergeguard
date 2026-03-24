"""MCP server for AI agent integration.

Exposes MergeGuard analysis capabilities as MCP tools that
AI coding agents can use to check for conflicts before
opening PRs.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from mergeguard.config import load_config
from mergeguard.core.engine import MergeGuardEngine
from mergeguard.core.merge_order import suggest_merge_order as _suggest_merge_order

logger = logging.getLogger(__name__)

_TOKEN_ENV_MAP = {
    "github": "GITHUB_TOKEN",
    "gitlab": "GITLAB_TOKEN",
    "bitbucket": "BITBUCKET_APP_PASSWORD",
}


def _get_mcp_token(platform: str) -> str:
    """Get API token from environment for the given platform."""
    env_var = _TOKEN_ENV_MAP.get(platform, "GITHUB_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(f"No token in env for platform {platform!r} (set {env_var})")
    return token


def _create_mcp_client(platform: str, repo: str, timeout: int = 30) -> Any:
    """Create an SCM client for the given platform."""
    token = _get_mcp_token(platform)
    if platform == "gitlab":
        from mergeguard.integrations.gitlab_client import GitLabClient

        gitlab_url = os.environ.get("GITLAB_URL", "https://gitlab.com")
        return GitLabClient(token, repo, gitlab_url)
    elif platform == "bitbucket":
        from mergeguard.integrations.bitbucket_client import BitbucketClient

        return BitbucketClient(token, repo)
    else:
        from mergeguard.integrations.github_client import GitHubClient

        config = load_config()
        return GitHubClient(
            token=token,
            repo_full_name=repo,
            base_url=config.github_url,
            timeout=timeout,
        )


def _serialize_conflicts(conflicts: list[Any]) -> list[dict[str, Any]]:
    """Convert Conflict model instances to plain dicts for JSON transport."""
    result = []
    for c in conflicts:
        result.append(
            {
                "conflict_type": c.conflict_type.value,
                "severity": c.severity.value,
                "source_pr": c.source_pr,
                "target_pr": c.target_pr,
                "file_path": c.file_path,
                "symbol_name": c.symbol_name,
                "description": c.description,
                "recommendation": c.recommendation,
                "source_lines": list(c.source_lines) if c.source_lines else None,
                "target_lines": list(c.target_lines) if c.target_lines else None,
                "cross_file": c.cross_file,
            }
        )
    return result


def create_mcp_server() -> Any:
    """Create and configure the MCP server.

    Exposes the following tools:
    - check_conflicts: Check if a set of file changes would conflict with open PRs
    - get_risk_score: Get the risk score for a specific PR
    - suggest_merge_order: Suggest optimal merge order for open PRs
    """
    try:
        from mcp.server import Server  # type: ignore[import-not-found]
    except ImportError:
        raise ImportError(
            "The 'mcp' package is required for MCP server functionality. "
            "Install it with: pip install mcp"
        ) from None

    server = Server("mergeguard")

    @server.tool("check_conflicts")  # type: ignore[untyped-decorator]
    async def check_conflicts(
        repo: str,
        files: list[str],
        platform: str = "github",
    ) -> dict[str, Any]:
        """Check if modifying the given files would conflict with open PRs.

        Args:
            repo: Repository in "owner/repo" format.
            files: List of file paths that will be modified.
            platform: SCM platform ("github", "gitlab", or "bitbucket").

        Returns:
            Dict with conflict analysis results including overlapping PRs
            and their details.
        """

        def _run() -> dict[str, Any]:
            try:
                client = _create_mcp_client(platform, repo)
            except ValueError as exc:
                return {"status": "error", "summary": str(exc)}
            config = load_config()
            try:
                open_prs = client.get_open_prs(
                    max_count=config.max_open_prs,
                    max_age_days=config.max_pr_age_days,
                )

                if not open_prs:
                    return {
                        "status": "ok",
                        "repo": repo,
                        "files_checked": files,
                        "total_open_prs": 0,
                        "conflicting_prs": [],
                        "summary": "No open PRs found in the repository.",
                    }

                target_files = set(files)
                conflicting_prs: list[dict[str, Any]] = []

                def _fetch_files(pr):  # type: ignore[no-untyped-def]
                    return pr, client.get_pr_files(pr.number)

                with ThreadPoolExecutor(max_workers=min(10, len(open_prs))) as pool:
                    futures = {pool.submit(_fetch_files, pr): pr for pr in open_prs}
                    for future in as_completed(futures):
                        pr, files_list = future.result()
                        pr.changed_files = files_list
                        overlap = target_files & pr.file_paths
                        if overlap:
                            conflicting_prs.append(
                                {
                                    "pr_number": pr.number,
                                    "title": pr.title,
                                    "author": pr.author,
                                    "head_branch": pr.head_branch,
                                    "overlapping_files": sorted(overlap),
                                    "total_files_changed": len(pr.file_paths),
                                }
                            )

                has_conflicts = len(conflicting_prs) > 0
                if has_conflicts:
                    pr_nums = [p["pr_number"] for p in conflicting_prs]
                    all_overlapping = set()
                    for p in conflicting_prs:
                        all_overlapping.update(p["overlapping_files"])
                    summary = (
                        f"{len(conflicting_prs)} open PR(s) touch the same files: "
                        f"{', '.join(f'#{n}' for n in pr_nums)}. "
                        f"Overlapping files: {', '.join(sorted(all_overlapping))}."
                    )
                else:
                    summary = (
                        f"No conflicts found. None of the {len(open_prs)} open PR(s) "
                        f"modify the specified files."
                    )

                return {
                    "status": "conflicts_found" if has_conflicts else "ok",
                    "repo": repo,
                    "files_checked": files,
                    "total_open_prs": len(open_prs),
                    "conflicting_prs": conflicting_prs,
                    "summary": summary,
                }
            finally:
                client.close()

        return await asyncio.to_thread(_run)

    @server.tool("get_risk_score")  # type: ignore[untyped-decorator]
    async def get_risk_score(
        repo: str,
        pr_number: int,
        platform: str = "github",
    ) -> dict[str, Any]:
        """Get the risk score for an open PR.

        Args:
            repo: Repository in "owner/repo" format.
            pr_number: PR number to analyze.
            platform: SCM platform ("github", "gitlab", or "bitbucket").

        Returns:
            Dict with risk score, factor breakdown, and conflict details.
        """

        def _run() -> dict[str, Any]:
            try:
                client = _create_mcp_client(platform, repo)
            except ValueError as exc:
                return {"status": "error", "summary": str(exc)}
            config = load_config()
            try:
                engine = MergeGuardEngine(
                    config=config,
                    client=client,
                )

                report = engine.analyze_pr(pr_number)

                severity_counts = report.conflict_count_by_severity

                return {
                    "status": "ok",
                    "repo": repo,
                    "pr_number": report.pr.number,
                    "pr_title": report.pr.title,
                    "pr_author": report.pr.author,
                    "risk_score": round(report.risk_score, 2),
                    "risk_factors": {k: round(v, 4) for k, v in report.risk_factors.items()},
                    "has_critical": report.has_critical,
                    "conflict_count": len(report.conflicts),
                    "conflict_severity_counts": severity_counts,
                    "conflicts": _serialize_conflicts(report.conflicts),
                    "no_conflict_prs": report.no_conflict_prs,
                    "analysis_duration_ms": report.analysis_duration_ms,
                    "summary": (
                        f"PR #{report.pr.number} '{report.pr.title}' has a risk score of "
                        f"{report.risk_score:.1f}/100 with {len(report.conflicts)} conflict(s)."
                    ),
                }
            finally:
                client.close()

        return await asyncio.to_thread(_run)

    @server.tool("suggest_merge_order")  # type: ignore[untyped-decorator]
    async def suggest_merge_order(
        repo: str,
        platform: str = "github",
    ) -> dict[str, Any]:
        """Suggest the optimal merge order for all open PRs.

        Args:
            repo: Repository in "owner/repo" format.
            platform: SCM platform ("github", "gitlab", or "bitbucket").

        Returns:
            Dict with suggested merge order, per-PR details, and reasoning.
        """

        def _run() -> dict[str, Any]:
            try:
                client = _create_mcp_client(platform, repo)
            except ValueError as exc:
                return {"status": "error", "summary": str(exc)}
            config = load_config()
            try:
                engine = MergeGuardEngine(
                    config=config,
                    client=client,
                )

                reports = engine.analyze_all_open_prs()

                if not reports:
                    return {
                        "status": "ok",
                        "repo": repo,
                        "total_prs": 0,
                        "merge_order": [],
                        "summary": "No open PRs found to order.",
                    }

                order = _suggest_merge_order(reports)

                report_map = {r.pr.number: r for r in reports}

                merge_order_details: list[dict[str, Any]] = []
                for position, (pr_number, reason) in enumerate(order, start=1):
                    report = report_map.get(pr_number)
                    entry: dict[str, Any] = {
                        "position": position,
                        "pr_number": pr_number,
                        "reason": reason,
                    }
                    if report:
                        entry["title"] = report.pr.title
                        entry["author"] = report.pr.author
                        entry["risk_score"] = round(report.risk_score, 2)
                        entry["conflict_count"] = len(report.conflicts)
                        entry["conflict_severity_counts"] = report.conflict_count_by_severity
                    merge_order_details.append(entry)

                total_conflicts = sum(len(r.conflicts) for r in reports)
                critical_count = sum(
                    1 for r in reports for c in r.conflicts if c.severity.value == "critical"
                )

                summary_parts = [
                    f"{len(reports)} open PR(s) analyzed.",
                    f"{total_conflicts} total conflict(s) detected",
                ]
                if critical_count > 0:
                    summary_parts.append(f"including {critical_count} critical")
                summary_parts.append(
                    f"Recommended first merge: PR #{order[0][0]}."
                    if order
                    else "No ordering needed."
                )

                return {
                    "status": "ok",
                    "repo": repo,
                    "total_prs": len(reports),
                    "total_conflicts": total_conflicts,
                    "critical_conflicts": critical_count,
                    "merge_order": merge_order_details,
                    "summary": ". ".join(summary_parts),
                }
            finally:
                client.close()

        return await asyncio.to_thread(_run)

    return server
