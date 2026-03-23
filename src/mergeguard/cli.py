"""MergeGuard CLI — Cross-PR intelligence from your terminal."""

from __future__ import annotations

import logging
import re as _re
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

if TYPE_CHECKING:
    from mergeguard.integrations.protocol import SCMClient
    from mergeguard.models import ConflictReport, PRInfo

logger = logging.getLogger(__name__)
console = Console(stderr=True)

_DEFAULT_BRANCHES = {"main", "master", "develop", "HEAD"}


def _detect_platform_from_remote() -> str:
    """Detect platform from git remote URL, defaulting to 'github'."""
    from mergeguard.integrations.git_local import GitLocalClient

    try:
        git_local = GitLocalClient()
        platform = git_local.detect_platform()
        return platform or "github"
    except ValueError:
        return "github"


def _create_client(
    platform: str,
    token: str | None,
    repo: str,
    gitlab_url: str,
    github_url: str | None = None,
) -> SCMClient:
    """Create the appropriate SCM client based on platform."""
    if token is None:
        raise click.UsageError(
            "A token is required. Provide --token or set GITHUB_TOKEN / GITLAB_TOKEN."
        )
    if platform == "auto":
        platform = _detect_platform_from_remote()
    if platform == "gitlab":
        from mergeguard.integrations.gitlab_client import GitLabClient

        return GitLabClient(token, repo, gitlab_url)
    elif platform == "bitbucket":
        from mergeguard.integrations.bitbucket_client import BitbucketClient

        return BitbucketClient(token, repo)
    else:
        from mergeguard.integrations.github_client import GitHubClient

        return GitHubClient(token, repo, base_url=github_url)


def _auto_detect_repo_and_pr(
    repo: str | None, pr: int | None, token: str | None, platform: str = "github"
) -> tuple[str, int]:
    """Auto-detect repo and PR from local git state.

    Raises click.UsageError on failure.
    """
    if repo is not None and pr is not None:
        return repo, pr

    from mergeguard.integrations.git_local import GitLocalClient

    try:
        git_local = GitLocalClient()
    except ValueError:
        raise click.UsageError(
            "Not in a git repository. Provide --repo and --pr explicitly."
        ) from None

    if repo is None:
        repo = git_local.get_repo_full_name()
        if repo is None:
            raise click.UsageError(
                "Could not detect repo from git remote. Provide --repo explicitly."
            )

    if pr is None:
        branch = git_local.get_current_branch()
        if branch in _DEFAULT_BRANCHES:
            raise click.UsageError(
                f"Current branch is '{branch}'. Switch to a feature branch "
                f"or provide --pr explicitly."
            )
        if token is None:
            raise click.UsageError(
                "A token is required to auto-detect the PR number. "
                "Provide --token or set GITHUB_TOKEN / GITLAB_TOKEN."
            )
        if platform == "gitlab":
            from mergeguard.integrations.gitlab_client import GitLabClient

            open_prs = GitLabClient(token, repo).get_open_prs()
        else:
            from mergeguard.integrations.github_client import GitHubClient

            open_prs = GitHubClient(token, repo).get_open_prs()
        matching = [p for p in open_prs if p.head_branch == branch]
        if not matching:
            raise click.UsageError(
                f"No open PR found for branch '{branch}'. Provide --pr explicitly."
            )
        if len(matching) > 1:
            matching.sort(key=lambda p: p.updated_at, reverse=True)
            console.print(
                f"[yellow]Multiple PRs for branch '{branch}', using most recent: "
                f"#{matching[0].number}[/yellow]"
            )
        pr = matching[0].number

    return repo, pr


def _auto_detect_repo(repo: str | None) -> str:
    """Auto-detect repo from local git state (for commands that don't need a PR)."""
    if repo is not None:
        return repo

    from mergeguard.integrations.git_local import GitLocalClient

    try:
        git_local = GitLocalClient()
    except ValueError:
        raise click.UsageError("Not in a git repository. Provide --repo explicitly.") from None

    repo = git_local.get_repo_full_name()
    if repo is None:
        raise click.UsageError("Could not detect repo from git remote. Provide --repo explicitly.")
    return repo


def _validate_repo(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    if value is not None and not _re.match(r"^[\w.-]+/[\w.-]+$", value):
        raise click.BadParameter("Must be in 'owner/repo' format")
    return value


@click.group()
@click.version_option(package_name="py-mergeguard")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging.")
@click.option(
    "--platform",
    type=click.Choice(["github", "gitlab", "bitbucket", "auto"]),
    default="auto",
    help="SCM platform (auto-detected from git remote by default).",
)
@click.option(
    "--gitlab-url",
    default="https://gitlab.com",
    help="GitLab instance URL (for self-hosted).",
)
@click.option(
    "--github-url",
    default=None,
    help="GitHub Enterprise Server URL (e.g., https://github.example.com).",
)
@click.pass_context
def main(
    ctx: click.Context, verbose: bool, platform: str, gitlab_url: str, github_url: str | None
) -> None:
    """MergeGuard: Cross-PR intelligence for the agentic coding era."""
    ctx.ensure_object(dict)
    ctx.obj["platform"] = platform
    ctx.obj["gitlab_url"] = gitlab_url
    ctx.obj["github_url"] = github_url
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


@main.command()
@click.option(
    "--repo",
    "-r",
    callback=_validate_repo,
    help="Repo (owner/repo). Auto-detected from git remote.",
)
@click.option(
    "--pr",
    "-p",
    type=click.IntRange(min=1),
    help="PR/MR number to analyze. Defaults to current branch.",
)
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"], help="GitHub/GitLab token.")
@click.option("--config", "-c", default=".mergeguard.yml", help="Config file path.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json", "markdown", "sarif", "html"]),
    default="terminal",
)
@click.option("--llm/--no-llm", default=False, help="Enable LLM-powered semantic analysis.")
@click.option(
    "--fix-suggestions/--no-fix-suggestions",
    default=False,
    help="Enhance fix suggestions with LLM analysis (templates always active).",
)
@click.option(
    "--llm-provider",
    type=click.Choice(["auto", "openai", "anthropic"]),
    default="auto",
    help="LLM provider to use (default: auto-detect from API keys).",
)
@click.option(
    "--post-comment/--no-post-comment",
    default=False,
    help="Post results as a PR/MR comment.",
)
@click.option(
    "--inline/--no-inline",
    default=None,
    help="Post inline annotations on PR diff.",
)
@click.option("--secrets/--no-secrets", default=None, help="Enable/disable secret scanning.")
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan (overrides config).")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days (overrides config).")
@click.option(
    "--exit-code/--no-exit-code",
    default=False,
    help="Exit non-zero on conflicts (1=any, 2=critical).",
)
@click.pass_context
def analyze(
    ctx: click.Context,
    repo: str | None,
    pr: int | None,
    token: str | None,
    config: str,
    output_format: str,
    llm: bool,
    fix_suggestions: bool,
    llm_provider: str,
    post_comment: bool,
    inline: bool | None,
    secrets: bool | None,
    max_prs: int | None,
    max_pr_age: int | None,
    exit_code: bool,
) -> None:
    """Analyze a PR for cross-PR conflicts."""
    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    resolved_platform = platform if platform != "auto" else _detect_platform_from_remote()
    repo, pr = _auto_detect_repo_and_pr(repo, pr, token, platform=resolved_platform)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    cfg = load_config(config)
    if fix_suggestions:
        cfg.fix_suggestions = True
        if not llm:
            import os as _os

            if _os.environ.get("OPENAI_API_KEY") or _os.environ.get("ANTHROPIC_API_KEY"):
                llm = True
    if llm:
        cfg.llm_enabled = True
    if llm_provider != "auto":
        cfg.llm_provider = llm_provider
    if max_prs is not None:
        cfg.max_open_prs = max_prs
    if max_pr_age is not None:
        cfg.max_pr_age_days = max_pr_age
    if github_url:
        cfg.github_url = github_url
    if secrets is not None:
        cfg.secrets.enabled = secrets

    client = _create_client(platform, token, repo, gitlab_url, github_url)
    with console.status("[bold blue]Analyzing cross-PR conflicts...", spinner="dots"):
        engine = MergeGuardEngine(config=cfg, client=client)
        report = engine.analyze_pr(pr)

    if output_format == "terminal":
        _display_terminal(report)
    elif output_format == "json":
        click.echo(report.model_dump_json(indent=2))
    elif output_format == "markdown":
        from mergeguard.output.github_comment import format_report

        click.echo(format_report(report, repo, platform=resolved_platform))
    elif output_format == "sarif":
        from mergeguard.output.sarif import format_sarif

        click.echo(format_sarif(report))
    elif output_format == "html":
        from mergeguard.output.html_report import format_html_report

        click.echo(format_html_report(report, repo))

    if post_comment and token:
        from mergeguard.output.github_comment import format_report
        from mergeguard.output.inline_annotations import (
            format_review_comments,
            format_review_summary,
        )

        # Determine inline setting: CLI flag > config > default (True)
        use_inline = inline if inline is not None else cfg.inline_annotations

        review_comments = []
        if use_inline:
            review_comments = format_review_comments(report, repo, platform=resolved_platform)

        # Post summary comment (always)
        markdown_body = format_report(
            report,
            repo,
            platform=resolved_platform,
            inline_count=len(review_comments),
        )
        client.post_pr_comment(pr, markdown_body)
        console.print("[green]\u2713 Comment posted to PR[/green]")

        # Post inline review (if comments exist)
        if review_comments:
            review_body = format_review_summary(report, len(review_comments))
            try:
                client.post_pr_review(pr, review_body, review_comments)
                console.print(
                    f"[green]\u2713 {len(review_comments)} inline annotation(s) posted[/green]"
                )
            except Exception as exc:
                logger.warning("Failed to post inline annotations: %s", exc)
                console.print(
                    "[yellow]\u26a0 Inline annotations failed (missing permissions?)[/yellow]"
                )

    if exit_code and report.conflicts:
        raise SystemExit(2 if report.has_critical else 1)


@main.command()
@click.option("--repo", "-r", callback=_validate_repo, help="Repo (owner/repo).")
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"])
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan.")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
)
@click.pass_context
def map(
    ctx: click.Context,
    repo: str | None,
    token: str | None,
    max_prs: int | None,
    max_pr_age: int | None,
    output_format: str,
) -> None:
    """Show the collision map of all open PRs."""
    import json as _json
    from collections import defaultdict
    from concurrent.futures import ThreadPoolExecutor

    repo = _auto_detect_repo(repo)

    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    client = _create_client(platform, token, repo, gitlab_url, github_url)
    prs = client.get_open_prs(max_count=max_prs or 200, max_age_days=max_pr_age or 30)

    # Enrich with file data (parallel)
    def fetch_files(pr_info: PRInfo) -> None:
        pr_info.changed_files = client.get_pr_files(pr_info.number)

    with ThreadPoolExecutor(max_workers=min(8, len(prs) or 1)) as executor:
        list(executor.map(fetch_files, prs))

    # Pre-compute all pairwise overlaps using a file→PR index
    file_to_prs: dict[str, set[int]] = defaultdict(set)
    for pr_info in prs:
        for cf in pr_info.changed_files:
            file_to_prs[cf.path].add(pr_info.number)

    overlap_files: dict[int, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for path, pr_numbers in file_to_prs.items():
        for a in pr_numbers:
            for b in pr_numbers:
                if a != b:
                    overlap_files[a][b].add(path)

    if output_format == "json":
        seen: set[tuple[int, int]] = set()
        overlaps: list[dict[str, object]] = []
        for a, partners in overlap_files.items():
            for b, files in partners.items():
                key = (min(a, b), max(a, b))
                if key not in seen:
                    seen.add(key)
                    overlaps.append(
                        {
                            "pr_a": key[0],
                            "pr_b": key[1],
                            "shared_files": sorted(files),
                        }
                    )
        click.echo(
            _json.dumps(
                {
                    "repo": repo,
                    "prs": [{"number": p.number, "title": p.title} for p in prs],
                    "overlaps": overlaps,
                },
                indent=2,
            )
        )
    else:
        table = Table(title=f"PR Collision Map \u2014 {repo}", show_lines=True)
        table.add_column("PR", style="bold cyan")
        for pr_info in prs:
            table.add_column(f"#{pr_info.number}", justify="center")

        for i, pr_a in enumerate(prs):
            row = [f"#{pr_a.number} {pr_a.title[:30]}"]
            for j, pr_b in enumerate(prs):
                if i == j:
                    row.append("\u2014")
                else:
                    count = len(overlap_files[pr_a.number].get(pr_b.number, set()))
                    if count > 0:
                        row.append(f"[red]{count} file(s)[/red]")
                    else:
                        row.append("[green]\u2713[/green]")
            table.add_row(*row)

        console.print(table)


@main.command()
@click.option("--repo", "-r", callback=_validate_repo, help="Repo (owner/repo).")
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"])
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan (overrides config).")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days (overrides config).")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "html", "json"]),
    default="terminal",
)
@click.pass_context
def dashboard(
    ctx: click.Context,
    repo: str | None,
    token: str | None,
    max_prs: int | None,
    max_pr_age: int | None,
    output_format: str,
) -> None:
    """Show risk scores for all open PRs."""
    repo = _auto_detect_repo(repo)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    cfg = load_config(".mergeguard.yml")
    if max_prs is not None:
        cfg.max_open_prs = max_prs
    if max_pr_age is not None:
        cfg.max_pr_age_days = max_pr_age
    client = _create_client(platform, token, repo, gitlab_url, github_url)
    engine = MergeGuardEngine(config=cfg, client=client)

    with console.status("[bold blue]Analyzing all open PRs...", spinner="dots"):
        reports = engine.analyze_all_open_prs()

    if output_format == "html":
        from mergeguard.output.dashboard_html import format_dashboard_html

        click.echo(format_dashboard_html(reports, repo))
        return

    if output_format == "json":
        import json as _json

        data = [
            {
                "pr": r.pr.number,
                "title": r.pr.title,
                "risk_score": round(r.risk_score, 1),
                "conflicts": len(r.conflicts),
                "ai": r.pr.ai_attribution.value,
            }
            for r in sorted(reports, key=lambda r: r.risk_score, reverse=True)
        ]
        click.echo(_json.dumps(data, indent=2))
        return

    table = Table(title=f"PR Risk Dashboard \u2014 {repo}")
    table.add_column("PR", style="bold")
    table.add_column("Title")
    table.add_column("Risk", justify="right")
    table.add_column("Conflicts", justify="right")
    table.add_column("AI?", justify="center")

    for report in sorted(reports, key=lambda r: r.risk_score, reverse=True):
        risk_style = (
            "red" if report.risk_score >= 70 else "yellow" if report.risk_score >= 40 else "green"
        )
        ai = "\U0001f916" if report.pr.ai_attribution.value.startswith("ai") else ""
        table.add_row(
            f"#{report.pr.number}",
            report.pr.title[:40],
            f"[{risk_style}]{report.risk_score:.0f}[/{risk_style}]",
            str(len(report.conflicts)),
            ai,
        )

    console.print(table)


@main.command("blast-radius")
@click.option(
    "--repo",
    "-r",
    callback=_validate_repo,
    help="Repo (owner/repo). Auto-detected from git remote.",
)
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"], help="GitHub/GitLab token.")
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan.")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "html", "json"]),
    default="html",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Write output to file instead of stdout.",
)
@click.pass_context
def blast_radius(
    ctx: click.Context,
    repo: str | None,
    token: str | None,
    max_prs: int | None,
    max_pr_age: int | None,
    output_format: str,
    output: str | None,
) -> None:
    """Visualize the blast radius of PR conflicts as an interactive graph."""
    repo = _auto_detect_repo(repo)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine
    from mergeguard.output.blast_radius import (
        build_blast_radius_data,
        format_blast_radius_html,
        format_blast_radius_json,
        format_blast_radius_terminal,
    )

    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    cfg = load_config(".mergeguard.yml")
    if max_prs is not None:
        cfg.max_open_prs = max_prs
    if max_pr_age is not None:
        cfg.max_pr_age_days = max_pr_age
    client = _create_client(platform, token, repo, gitlab_url, github_url)
    engine = MergeGuardEngine(config=cfg, client=client)

    with console.status("[bold blue]Analyzing blast radius...", spinner="dots"):
        reports = engine.analyze_all_open_prs()
        file_graph = None
        if output_format == "html":
            prs = [r.pr for r in reports]
            file_graph = engine.build_file_dependency_graph(prs)
        data = build_blast_radius_data(reports, repo, file_graph)

    if output_format == "terminal":
        format_blast_radius_terminal(data)
    elif output_format == "json":
        result = format_blast_radius_json(data)
        if output:
            from pathlib import Path

            Path(output).write_text(result)
            console.print(f"[green]\u2713 JSON written to {output}[/green]")
        else:
            click.echo(result)
    else:
        result = format_blast_radius_html(data)
        if output:
            from pathlib import Path

            Path(output).write_text(result)
            console.print(f"[green]\u2713 HTML written to {output}[/green]")
        else:
            click.echo(result)


@main.command("policy-check")
@click.option(
    "--repo",
    "-r",
    callback=_validate_repo,
    help="Repo (owner/repo). Auto-detected from git remote.",
)
@click.option(
    "--pr",
    "-p",
    type=click.IntRange(min=1),
    help="PR/MR number to analyze. Defaults to current branch.",
)
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"], help="GitHub/GitLab token.")
@click.option("--config", "-c", default=".mergeguard.yml", help="Config file path.")
@click.option(
    "--dry-run/--execute",
    default=True,
    help="Dry run (default) shows what would happen; --execute runs actions.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
)
@click.pass_context
def policy_check(
    ctx: click.Context,
    repo: str | None,
    pr: int | None,
    token: str | None,
    config: str,
    dry_run: bool,
    output_format: str,
) -> None:
    """Evaluate policy rules against a PR's conflict analysis."""
    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    resolved_platform = platform if platform != "auto" else _detect_platform_from_remote()
    repo, pr = _auto_detect_repo_and_pr(repo, pr, token, platform=resolved_platform)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    cfg = load_config(config)
    if not cfg.policy.enabled:
        console.print("[yellow]Policy engine is not enabled in config.[/yellow]")
        console.print("[dim]Add 'policy.enabled: true' to .mergeguard.yml[/dim]")
        return

    if github_url:
        cfg.github_url = github_url

    client = _create_client(platform, token, repo, gitlab_url, github_url)
    with console.status("[bold blue]Analyzing PR and evaluating policies...", spinner="dots"):
        engine = MergeGuardEngine(config=cfg, client=client)
        report = engine.analyze_pr(pr)

        from mergeguard.core.policy import evaluate_policies, execute_policy_actions

        evaluation = evaluate_policies(report, cfg.policy)

    if output_format == "json":
        click.echo(evaluation.model_dump_json(indent=2))
        return

    # Terminal output
    table = Table(title=f"Policy Evaluation — PR #{pr}")
    table.add_column("Policy", style="bold")
    table.add_column("Match", justify="center")
    table.add_column("Actions")

    for result in evaluation.results:
        match_str = "[green]YES[/green]" if result.matched else "[dim]no[/dim]"
        actions_str = (
            ", ".join(a.action.value for a in result.actions_to_execute) if result.matched else ""
        )
        table.add_row(result.policy_name, match_str, actions_str)

    console.print(table)

    if evaluation.has_block:
        console.print("\n[red bold]MERGE BLOCKED by policy.[/red bold]")

    if evaluation.matched_policies:
        console.print(
            f"\n[bold]{len(evaluation.matched_policies)} policy/policies matched, "
            f"{len(evaluation.actions)} action(s) queued.[/bold]"
        )
    else:
        console.print("\n[green]No policies triggered.[/green]")

    if not dry_run and evaluation.actions:
        console.print("\n[bold blue]Executing actions...[/bold blue]")
        log = execute_policy_actions(report, evaluation, client, repo, resolved_platform)
        for entry in log:
            status = "[green]OK[/green]" if entry.get("success") else "[red]FAIL[/red]"
            console.print(f"  {status} {entry['action']}")


def _display_terminal(report: ConflictReport) -> None:
    """Rich terminal display for a single PR analysis."""

    if not report.conflicts:
        console.print(
            f"\n[green]\u2705 PR #{report.pr.number} has no cross-PR conflicts![/green]\n"
        )
        return

    console.print(f"\n[bold]MergeGuard Report \u2014 PR #{report.pr.number}[/bold]")
    console.print(f"Risk Score: {report.risk_score:.0f}/100\n")

    for conflict in report.conflicts:
        sev_color = {"critical": "red", "warning": "yellow", "info": "dim"}
        color = sev_color.get(conflict.severity.value, "white")
        console.print(
            f"  [{color}]\u25cf {conflict.severity.value.upper()}[/{color}] "
            f"{conflict.conflict_type.value} with #{conflict.target_pr}"
        )
        console.print(f"    File: {conflict.file_path}")
        if conflict.symbol_name:
            console.print(f"    Symbol: {conflict.symbol_name}")
        console.print(f"    {conflict.description}")
        console.print(f"    \U0001f4a1 {conflict.recommendation}")
        if conflict.fix_suggestion is not None:
            console.print(f"    \U0001f527 {conflict.fix_suggestion}")
        if conflict.source_diff_preview or conflict.target_diff_preview:
            from mergeguard.output.terminal import _render_diff_previews

            _render_diff_previews(conflict)
        console.print()

    if report.pr.skipped_files:
        console.print("[dim]Files skipped (no patch data):[/dim]")
        for path in report.pr.skipped_files:
            console.print(f"  [dim]- {path}[/dim]")


@main.command("suggest-order")
@click.option("--repo", "-r", callback=_validate_repo, help="Repo (owner/repo).")
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"])
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan.")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days.")
@click.pass_context
def suggest_order(
    ctx: click.Context,
    repo: str | None,
    token: str | None,
    max_prs: int | None,
    max_pr_age: int | None,
) -> None:
    """Suggest optimal merge order for open PRs."""
    repo = _auto_detect_repo(repo)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    cfg = load_config(".mergeguard.yml")
    if max_prs is not None:
        cfg.max_open_prs = max_prs
    if max_pr_age is not None:
        cfg.max_pr_age_days = max_pr_age
    client = _create_client(platform, token, repo, gitlab_url, github_url)
    engine = MergeGuardEngine(config=cfg, client=client)

    with console.status("[bold blue]Analyzing merge order...", spinner="dots"):
        reports = engine.analyze_all_open_prs()

    from mergeguard.core.merge_order import format_merge_order, suggest_merge_order

    order = suggest_merge_order(reports)
    console.print(format_merge_order(order, reports))


@main.command()
@click.option("--repo", "-r", callback=_validate_repo, help="Repo (owner/repo).")
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"])
@click.option("--interval", type=int, default=60, help="Poll interval in seconds.")
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan.")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days.")
@click.option(
    "--post-comment/--no-post-comment",
    default=True,
    help="Auto-post/update PR comments.",
)
@click.pass_context
def watch(
    ctx: click.Context,
    repo: str | None,
    token: str | None,
    interval: int,
    max_prs: int | None,
    max_pr_age: int | None,
    post_comment: bool,
) -> None:
    """Watch for PR changes and re-analyze automatically."""
    import time as _time

    repo = _auto_detect_repo(repo)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    resolved_platform = platform if platform != "auto" else _detect_platform_from_remote()
    cfg = load_config(".mergeguard.yml")
    if max_prs is not None:
        cfg.max_open_prs = max_prs
    if max_pr_age is not None:
        cfg.max_pr_age_days = max_pr_age
    client = _create_client(platform, token, repo, gitlab_url, github_url)

    # Track head SHAs to detect changes
    known_shas: dict[int, str] = {}
    console.print(f"[bold blue]Watching {repo} (every {interval}s)...[/bold blue]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        while True:
            prs = client.get_open_prs(
                max_count=max_prs or cfg.max_open_prs,
                max_age_days=max_pr_age or cfg.max_pr_age_days,
            )

            changed_prs: list[int] = []
            for pr_info in prs:
                old_sha = known_shas.get(pr_info.number)
                if old_sha != pr_info.head_sha:
                    if old_sha is not None:
                        changed_prs.append(pr_info.number)
                    known_shas[pr_info.number] = pr_info.head_sha

            # Detect new PRs
            current_numbers = {p.number for p in prs}
            new_prs = current_numbers - set(known_shas.keys())
            if new_prs:
                changed_prs.extend(new_prs)
                for n in new_prs:
                    pr_info = next(p for p in prs if p.number == n)
                    known_shas[n] = pr_info.head_sha

            # Remove closed PRs from tracking
            closed = set(known_shas.keys()) - current_numbers
            for n in closed:
                del known_shas[n]

            if changed_prs:
                console.print(
                    f"[yellow]Changes detected in PRs: "
                    f"{', '.join(f'#{n}' for n in changed_prs)}[/yellow]"
                )
                engine = MergeGuardEngine(config=cfg, client=client)
                for pr_num in changed_prs:
                    try:
                        report = engine.analyze_pr(pr_num)
                        _display_terminal(report)
                        if post_comment and token and report.conflicts:
                            from mergeguard.output.github_comment import format_report

                            comment = format_report(report, repo, platform=resolved_platform)
                            client.post_pr_comment(pr_num, comment)
                            console.print(f"[green]\u2713 Comment updated on PR #{pr_num}[/green]")
                    except Exception:
                        console.print(
                            f"[red]Failed to analyze PR #{pr_num}[/red]",
                        )
            else:
                console.print(f"[dim]{_time.strftime('%H:%M:%S')} — no changes[/dim]")

            _time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[bold]Watch stopped.[/bold]")


@main.command()
@click.option("--repo", "-r", callback=_validate_repo, help="Repo (owner/repo).")
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"])
@click.option("--limit", type=int, default=20, help="Number of history entries to show.")
@click.pass_context
def history(
    ctx: click.Context,
    repo: str | None,
    token: str | None,
    limit: int,
) -> None:
    """Show historical analysis results."""
    from mergeguard.storage.decisions_log import DecisionsLog

    try:
        log = DecisionsLog()
    except Exception:
        console.print("[red]No decisions log found. Run an analysis first.[/red]")
        return

    decisions = log.get_recent_decisions(limit=limit)
    log.close()

    if not decisions:
        console.print("[dim]No history entries found.[/dim]")
        return

    table = Table(title="Analysis History")
    table.add_column("PR", style="bold")
    table.add_column("Type")
    table.add_column("Entity")
    table.add_column("Merged At")
    table.add_column("Author")

    for entry in decisions:
        table.add_row(
            f"#{entry.pr_number}",
            entry.decision_type.value,
            entry.entity[:40],
            entry.merged_at.strftime("%Y-%m-%d %H:%M"),
            entry.author,
        )

    console.print(table)


@main.command(name="scan-secrets")
@click.option(
    "--repo",
    "-r",
    callback=_validate_repo,
    help="Repo (owner/repo). Auto-detected from git remote.",
)
@click.option(
    "--pr",
    "-p",
    type=click.IntRange(min=1),
    help="PR/MR number to scan. Defaults to current branch.",
)
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"], help="GitHub/GitLab token.")
@click.option("--config", "-c", default=".mergeguard.yml", help="Config file path.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json", "sarif"]),
    default="terminal",
)
@click.pass_context
def scan_secrets_cmd(
    ctx: click.Context,
    repo: str | None,
    pr: int | None,
    token: str | None,
    config: str,
    output_format: str,
) -> None:
    """Scan a PR for accidentally committed secrets."""
    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    resolved_platform = platform if platform != "auto" else _detect_platform_from_remote()
    repo, pr = _auto_detect_repo_and_pr(repo, pr, token, platform=resolved_platform)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine
    from mergeguard.models import ConflictType

    cfg = load_config(config)
    cfg.secrets.enabled = True
    if github_url:
        cfg.github_url = github_url

    client = _create_client(platform, token, repo, gitlab_url, github_url)
    with console.status("[bold blue]Scanning for secrets...", spinner="dots"):
        engine = MergeGuardEngine(config=cfg, client=client)
        report = engine.analyze_pr(pr)

    # Filter to only secret findings
    report.conflicts = [c for c in report.conflicts if c.conflict_type == ConflictType.SECRET]

    if output_format == "json":
        click.echo(report.model_dump_json(indent=2))
    elif output_format == "sarif":
        from mergeguard.output.sarif import format_sarif

        click.echo(format_sarif(report))
    else:
        # Terminal output
        if not report.conflicts:
            console.print("[green]No secrets detected.[/green]")
            return

        table = Table(title=f"Secrets Found in PR #{pr}")
        table.add_column("File", style="bold")
        table.add_column("Line", justify="right")
        table.add_column("Pattern")
        table.add_column("Severity")

        for conflict in report.conflicts:
            line_str = str(conflict.source_lines[0]) if conflict.source_lines else "-"
            sev_style = "red" if conflict.severity.value == "critical" else "yellow"
            table.add_row(
                conflict.file_path,
                line_str,
                conflict.symbol_name or "-",
                f"[{sev_style}]{conflict.severity.value.upper()}[/{sev_style}]",
            )

        console.print(table)
        console.print(
            f"\n[bold red]{len(report.conflicts)} secret(s) found.[/bold red] "
            f"Remove them and rotate immediately."
        )


@main.command()
@click.option("--repo", "-r", callback=_validate_repo, help="Repo (owner/repo).")
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"])
@click.option("--config", "-c", default=".mergeguard.yml", help="Config file path.")
@click.option(
    "--window",
    "-w",
    "windows",
    multiple=True,
    type=int,
    help="Time window in days (can specify multiple). Defaults to 7, 30, 90.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json", "html"]),
    default="terminal",
)
@click.pass_context
def metrics(
    ctx: click.Context,
    repo: str | None,
    token: str | None,
    config: str,
    windows: tuple[int, ...],
    output_format: str,
) -> None:
    """Show DORA metrics for conflict resolution tracking."""
    repo = _auto_detect_repo(repo)

    from mergeguard.config import load_config
    from mergeguard.core.metrics import compute_dora_metrics

    cfg = load_config(config)
    if not cfg.metrics.enabled:
        console.print("[yellow]Metrics tracking is not enabled in config.[/yellow]")
        console.print("[dim]Add 'metrics.enabled: true' to .mergeguard.yml[/dim]")
        return

    time_windows = list(windows) if windows else cfg.metrics.time_windows

    with console.status("[bold blue]Computing DORA metrics...", spinner="dots"):
        report = compute_dora_metrics(repo, time_windows)

    if output_format == "json":
        click.echo(report.model_dump_json(indent=2))
        return

    if output_format == "html":
        from mergeguard.output.metrics_html import format_metrics_html

        click.echo(format_metrics_html(report))
        return

    # Terminal output
    for window in report.windows:
        table = Table(title=f"DORA Metrics — {repo} ({window.window_days}d window)")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        # Merge frequency
        table.add_row("Merge Count", str(window.merge_count))
        table.add_row("Merges/Day", f"{window.merges_per_day:.2f}")

        # Conflict rate
        rate_pct = window.conflict_rate * 100
        rate_color = "green" if rate_pct < 20 else "yellow" if rate_pct < 50 else "red"
        table.add_row(
            "Conflict Rate",
            f"[{rate_color}]{rate_pct:.1f}%[/{rate_color}]",
        )
        table.add_row("PRs Analyzed", str(window.total_prs_analyzed))
        table.add_row("PRs w/ Conflicts", str(window.prs_with_conflicts))

        # Resolution times
        mean_h = window.mean_resolution_time_hours
        mean_color = "green" if mean_h < 24 else "yellow" if mean_h < 72 else "red"
        table.add_row(
            "Mean Resolution",
            f"[{mean_color}]{mean_h:.1f}h[/{mean_color}]",
        )
        table.add_row("Median Resolution", f"{window.median_resolution_time_hours:.1f}h")
        table.add_row("P90 Resolution", f"{window.p90_resolution_time_hours:.1f}h")

        # MTTRC
        mttrc_h = window.mttrc_hours
        mttrc_color = "green" if mttrc_h < 24 else "yellow" if mttrc_h < 72 else "red"
        table.add_row(
            "MTTRC",
            f"[{mttrc_color}]{mttrc_h:.1f}h[/{mttrc_color}]",
        )

        # Unresolved
        uc = window.unresolved_count
        unresolved_color = "green" if uc == 0 else "yellow" if uc < 5 else "red"
        table.add_row(
            "Unresolved",
            f"[{unresolved_color}]{window.unresolved_count}[/{unresolved_color}]",
        )

        console.print(table)
        console.print()


@main.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Interactive setup wizard — generates a .mergeguard.yml config."""
    from pathlib import Path

    config_path = Path(".mergeguard.yml")
    if config_path.exists() and not click.confirm(".mergeguard.yml already exists. Overwrite?"):
        return

    # Detect repo characteristics
    console.print("[bold]MergeGuard Setup Wizard[/bold]\n")

    # Detect languages
    try:
        from mergeguard.integrations.git_local import GitLocalClient

        GitLocalClient()  # Verify we're in a git repo
        console.print("[dim]Detecting project languages...[/dim]")
    except ValueError:
        pass

    # Ask workflow questions
    risk_threshold = click.prompt(
        "Risk threshold (only comment if score exceeds this)",
        type=int,
        default=50,
    )
    max_pr_age = click.prompt(
        "Max PR age in days (only scan recent PRs)",
        type=int,
        default=30,
    )
    llm_enabled = click.confirm("Enable LLM-powered semantic analysis?", default=False)

    # Check for monorepo indicators
    is_monorepo = Path("packages").is_dir() or Path("apps").is_dir() or Path("services").is_dir()
    if is_monorepo:
        console.print("[yellow]Monorepo detected![/yellow] Adding cross-module guardrails.\n")

    # Build config
    config_lines = [
        "# MergeGuard Configuration",
        "# Generated by `mergeguard init`",
        "",
        f"risk_threshold: {risk_threshold}",
        "check_regressions: true",
        "max_open_prs: 200",
        f"max_pr_age_days: {max_pr_age}",
        "decisions_log_depth: 50",
        "",
        f"llm_enabled: {'true' if llm_enabled else 'false'}",
    ]

    if llm_enabled:
        config_lines.append('llm_model: "claude-sonnet-4-20250514"')

    config_lines.extend(
        [
            "",
            "ignored_paths:",
            '  - "*.lock"',
            '  - "*.min.js"',
            '  - "*.min.css"',
            '  - "package-lock.json"',
            '  - "yarn.lock"',
            '  - "pnpm-lock.yaml"',
            '  - "poetry.lock"',
        ]
    )

    if is_monorepo:
        config_lines.extend(
            [
                "",
                "# Monorepo guardrails (customize patterns for your project)",
                "# rules:",
                "#   - name: cross-module-boundary",
                '#     pattern: "packages/billing/**"',
                "#     cannot_import_from:",
                '#       - "packages/auth/**"',
                '#     message: "Billing must not import from auth directly"',
            ]
        )

    config_text = "\n".join(config_lines) + "\n"
    config_path.write_text(config_text)
    console.print(f"\n[green]\u2713 Created {config_path}[/green]")

    # Offer to create GitHub Actions workflow
    if click.confirm("\nCreate GitHub Actions workflow?", default=True):
        workflows_dir = Path(".github/workflows")
        workflows_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = workflows_dir / "mergeguard.yml"
        workflow_text = """name: MergeGuard
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write
  contents: read

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Vansh2795/mergeguard@main
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
"""
        workflow_path.write_text(workflow_text)
        console.print(f"[green]\u2713 Created {workflow_path}[/green]")

    console.print(
        "\n[bold green]Setup complete![/bold green] Run `mergeguard analyze` to get started."
    )


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind address.")
@click.option("--port", type=int, default=8000, help="Port to listen on.")
@click.option("--workers", type=int, default=1, help="Number of uvicorn workers.")
@click.pass_context
def serve(
    ctx: click.Context,
    host: str,
    port: int,
    workers: int,
) -> None:
    """Start the webhook server for real-time conflict detection."""
    try:
        import uvicorn
    except ImportError:
        raise click.UsageError(
            "The server extra is required: pip install py-mergeguard[server]"
        ) from None

    console.print(f"[bold blue]Starting MergeGuard webhook server on {host}:{port}[/bold blue]")
    console.print("[dim]Endpoints:[/dim]")
    console.print("  POST /webhooks/github")
    console.print("  POST /webhooks/gitlab")
    console.print("  POST /webhooks/bitbucket")
    console.print("  GET  /health")
    console.print("  GET  /metrics")
    console.print()

    uvicorn.run(
        "mergeguard.server.webhook:app",
        host=host,
        port=port,
        workers=workers,
        log_level="info",
    )


@main.command("analyze-multi")
@click.option(
    "--config",
    "-c",
    "config_path",
    default=".mergeguard-multi.yml",
    help="Multi-repo config file.",
)
@click.option("--token", "-t", envvar=["GITHUB_TOKEN", "GITLAB_TOKEN"], help="API token.")
@click.pass_context
def analyze_multi(
    ctx: click.Context,
    config_path: str,
    token: str | None,
) -> None:
    """Analyze conflicts across multiple related repositories."""
    from pathlib import Path

    import yaml

    path = Path(config_path)
    if not path.exists():
        raise click.UsageError(
            f"Multi-repo config not found: {config_path}\n"
            f"Create a .mergeguard-multi.yml with:\n"
            f"  repos:\n"
            f"    - name: shared-lib\n      repo: org/shared-lib\n"
            f"    - name: service-a\n      repo: org/service-a\n"
            f"      depends_on: [shared-lib]"
        )

    with open(path) as f:
        multi_config = yaml.safe_load(f)

    if not multi_config or "repos" not in multi_config:
        raise click.UsageError("Invalid multi-repo config: missing 'repos' key")

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    platform = ctx.obj.get("platform", "auto")
    gitlab_url = ctx.obj.get("gitlab_url", "https://gitlab.com")
    github_url = ctx.obj.get("github_url")
    resolved_platform = platform if platform != "auto" else _detect_platform_from_remote()

    all_reports = []
    repo_names: dict[str, str] = {}  # repo_path -> friendly name

    for repo_entry in multi_config["repos"]:
        repo_path = repo_entry["repo"]
        repo_name = repo_entry.get("name", repo_path)
        repo_names[repo_path] = repo_name

        console.print(f"\n[bold cyan]Analyzing {repo_name} ({repo_path})...[/bold cyan]")

        cfg = load_config(".mergeguard.yml")
        client = _create_client(resolved_platform, token, repo_path, gitlab_url, github_url)
        engine = MergeGuardEngine(config=cfg, client=client)

        with console.status(f"[bold blue]Scanning {repo_name}...", spinner="dots"):
            reports = engine.analyze_all_open_prs()

        for report in reports:
            all_reports.append((repo_name, report))

    # Display combined results
    console.print(f"\n[bold]Multi-Repo Summary ({len(all_reports)} PRs)[/bold]\n")
    table = Table(title="Cross-Repo Risk Dashboard")
    table.add_column("Repo", style="cyan")
    table.add_column("PR", style="bold")
    table.add_column("Title")
    table.add_column("Risk", justify="right")
    table.add_column("Conflicts", justify="right")

    for repo_name, report in sorted(all_reports, key=lambda x: x[1].risk_score, reverse=True):
        risk_style = (
            "red" if report.risk_score >= 70 else "yellow" if report.risk_score >= 40 else "green"
        )
        table.add_row(
            repo_name,
            f"#{report.pr.number}",
            report.pr.title[:35],
            f"[{risk_style}]{report.risk_score:.0f}[/{risk_style}]",
            str(len(report.conflicts)),
        )

    console.print(table)
