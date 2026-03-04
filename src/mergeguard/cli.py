"""MergeGuard CLI — Cross-PR intelligence from your terminal."""

from __future__ import annotations

import logging
import re as _re

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

console = Console(stderr=True)

_DEFAULT_BRANCHES = {"main", "master", "develop", "HEAD"}


def _auto_detect_repo_and_pr(repo, pr, token):
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
        )

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
                f"Current branch is '{branch}'. Switch to a feature branch or provide --pr explicitly."
            )
        if token is None:
            raise click.UsageError(
                "A GitHub token is required to auto-detect the PR number. "
                "Provide --token or set GITHUB_TOKEN."
            )
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


def _auto_detect_repo(repo):
    """Auto-detect repo from local git state (for commands that don't need a PR)."""
    if repo is not None:
        return repo

    from mergeguard.integrations.git_local import GitLocalClient

    try:
        git_local = GitLocalClient()
    except ValueError:
        raise click.UsageError(
            "Not in a git repository. Provide --repo explicitly."
        )

    repo = git_local.get_repo_full_name()
    if repo is None:
        raise click.UsageError(
            "Could not detect repo from git remote. Provide --repo explicitly."
        )
    return repo


def _validate_repo(ctx, param, value):
    if value is not None and not _re.match(r'^[\w.-]+/[\w.-]+$', value):
        raise click.BadParameter("Must be in 'owner/repo' format")
    return value


@click.group()
@click.version_option(package_name="py-mergeguard")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging.")
@click.pass_context
def main(ctx, verbose):
    """MergeGuard: Cross-PR intelligence for the agentic coding era."""
    ctx.ensure_object(dict)
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


@main.command()
@click.option("--repo", "-r", callback=_validate_repo, help="GitHub repo (owner/repo). Auto-detected from git remote.")
@click.option("--pr", "-p", type=click.IntRange(min=1), help="PR number to analyze. Defaults to current branch.")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub token.")
@click.option("--config", "-c", default=".mergeguard.yml", help="Config file path.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json", "markdown"]),
    default="terminal",
)
@click.option("--llm/--no-llm", default=False, help="Enable LLM-powered semantic analysis.")
@click.option(
    "--post-comment/--no-post-comment",
    default=False,
    help="Post results as a GitHub PR comment.",
)
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan (overrides config).")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days (overrides config).")
def analyze(repo, pr, token, config, output_format, llm, post_comment, max_prs, max_pr_age):
    """Analyze a PR for cross-PR conflicts."""
    repo, pr = _auto_detect_repo_and_pr(repo, pr, token)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    cfg = load_config(config)
    if llm:
        cfg.llm_enabled = True
    if max_prs is not None:
        cfg.max_open_prs = max_prs
    if max_pr_age is not None:
        cfg.max_pr_age_days = max_pr_age

    with console.status("[bold blue]Analyzing cross-PR conflicts...", spinner="dots"):
        engine = MergeGuardEngine(
            token=token,
            repo_full_name=repo,
            config=cfg,
        )
        report = engine.analyze_pr(pr)

    if output_format == "terminal":
        _display_terminal(report)
    elif output_format == "json":
        click.echo(report.model_dump_json(indent=2))
    elif output_format == "markdown":
        from mergeguard.output.github_comment import format_report

        click.echo(format_report(report, repo))

    if post_comment and token:
        from mergeguard.integrations.github_client import GitHubClient
        from mergeguard.output.github_comment import format_report

        client = GitHubClient(token, repo)
        client.post_pr_comment(pr, format_report(report, repo))
        console.print("[green]\u2713 Comment posted to PR[/green]")


@main.command()
@click.option("--repo", "-r", callback=_validate_repo, help="GitHub repo (owner/repo).")
@click.option("--token", "-t", envvar="GITHUB_TOKEN")
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan.")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days.")
def map(repo, token, max_prs, max_pr_age):
    """Show the collision map of all open PRs."""
    repo = _auto_detect_repo(repo)

    from collections import defaultdict
    from concurrent.futures import ThreadPoolExecutor

    from mergeguard.integrations.github_client import GitHubClient

    client = GitHubClient(token, repo)
    prs = client.get_open_prs(max_count=max_prs or 200, max_age_days=max_pr_age or 30)

    # Enrich with file data (parallel)
    def fetch_files(pr_info):
        pr_info.changed_files = client.get_pr_files(pr_info.number)

    with ThreadPoolExecutor(max_workers=min(8, len(prs) or 1)) as executor:
        list(executor.map(fetch_files, prs))

    # Pre-compute all pairwise overlaps using a file→PR index
    file_to_prs: dict[str, set[int]] = defaultdict(set)
    for pr_info in prs:
        for cf in pr_info.changed_files:
            file_to_prs[cf.path].add(pr_info.number)

    overlap_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for path, pr_numbers in file_to_prs.items():
        for a in pr_numbers:
            for b in pr_numbers:
                if a != b:
                    overlap_counts[a][b] += 1

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
                count = overlap_counts[pr_a.number].get(pr_b.number, 0)
                if count > 0:
                    row.append(f"[red]{count} file(s)[/red]")
                else:
                    row.append("[green]\u2713[/green]")
        table.add_row(*row)

    console.print(table)


@main.command()
@click.option("--repo", "-r", callback=_validate_repo, help="GitHub repo (owner/repo).")
@click.option("--token", "-t", envvar="GITHUB_TOKEN")
@click.option("--max-prs", type=int, default=None, help="Max open PRs to scan (overrides config).")
@click.option("--max-pr-age", type=int, default=None, help="Max PR age in days (overrides config).")
def dashboard(repo, token, max_prs, max_pr_age):
    """Show risk scores for all open PRs."""
    repo = _auto_detect_repo(repo)

    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    cfg = load_config(".mergeguard.yml")
    if max_prs is not None:
        cfg.max_open_prs = max_prs
    if max_pr_age is not None:
        cfg.max_pr_age_days = max_pr_age
    engine = MergeGuardEngine(token=token, repo_full_name=repo, config=cfg)

    with console.status("[bold blue]Analyzing all open PRs...", spinner="dots"):
        reports = engine.analyze_all_open_prs()

    table = Table(title=f"PR Risk Dashboard \u2014 {repo}")
    table.add_column("PR", style="bold")
    table.add_column("Title")
    table.add_column("Risk", justify="right")
    table.add_column("Conflicts", justify="right")
    table.add_column("AI?", justify="center")

    for report in sorted(reports, key=lambda r: r.risk_score, reverse=True):
        risk_style = (
            "red"
            if report.risk_score >= 70
            else "yellow"
            if report.risk_score >= 40
            else "green"
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


def _display_terminal(report):
    """Rich terminal display for a single PR analysis."""
    from mergeguard.models import ConflictSeverity

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
        console.print(f"    \U0001f4a1 {conflict.recommendation}\n")

    if report.pr.skipped_files:
        console.print("[dim]Files skipped (no patch data):[/dim]")
        for path in report.pr.skipped_files:
            console.print(f"  [dim]- {path}[/dim]")
