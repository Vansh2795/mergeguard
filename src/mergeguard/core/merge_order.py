"""Suggest optimal merge order based on inter-PR conflict graph.

Builds a weighted conflict graph from ConflictReport objects and greedily
selects the PR with the lowest total outgoing conflict weight at each step.
After each selection, edges for the merged PR are removed and weights
recalculated for the remaining nodes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from mergeguard.models import ConflictReport, ConflictSeverity

# Severity weights used when scoring edges in the conflict graph.
SEVERITY_WEIGHT: dict[ConflictSeverity, int] = {
    ConflictSeverity.CRITICAL: 10,
    ConflictSeverity.WARNING: 3,
    ConflictSeverity.INFO: 1,
}


def _build_conflict_graph(
    reports: list[ConflictReport],
) -> tuple[set[int], dict[int, dict[int, int]]]:
    """Build an adjacency map of PR -> {neighbor_pr: total_weight}.

    Returns the set of all PR numbers and the weighted adjacency dict.
    Edges are bidirectional: if PR A conflicts with PR B, both
    A->B and B->A get the weight added.
    """
    prs: set[int] = {r.pr.number for r in reports}
    graph: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    for report in reports:
        src = report.pr.number
        for conflict in report.conflicts:
            tgt = conflict.target_pr
            weight = SEVERITY_WEIGHT.get(conflict.severity, 1)
            graph[src][tgt] += weight
            graph[tgt][src] += weight

    return prs, graph


def _total_weight(pr: int, graph: dict[int, dict[int, int]]) -> int:
    """Sum of all outgoing edge weights for a PR."""
    return sum(graph.get(pr, {}).values())


def _remove_pr(pr: int, graph: dict[int, dict[int, int]]) -> None:
    """Remove a PR node and all its edges from the graph in-place."""
    neighbors = list(graph.pop(pr, {}).keys())
    for neighbor in neighbors:
        graph[neighbor].pop(pr, None)


def _build_reason(
    pr_number: int,
    graph: dict[int, dict[int, int]],
    remaining_count: int,
) -> str:
    """Build a human-readable reason string for why this PR is next."""
    total = _total_weight(pr_number, graph)
    neighbors = graph.get(pr_number, {})

    if total == 0:
        return "No conflicts with remaining PRs"

    conflict_parts: list[str] = []
    for neighbor, weight in sorted(neighbors.items(), key=lambda kv: -kv[1]):
        conflict_parts.append(f"#{neighbor} (weight {weight})")

    summary = ", ".join(conflict_parts)
    return f"Conflict weight {total} across {len(neighbors)} PR(s): {summary}"


def suggest_merge_order(
    reports: list[ConflictReport],
) -> list[tuple[int, str]]:
    """Suggest optimal merge order based on conflict graph.

    Uses a greedy strategy: at each step, pick the PR whose total conflict
    weight against *remaining* PRs is lowest. Ties are broken by PR number
    (lower first) so the output is deterministic.

    Returns list of (pr_number, reason) tuples in suggested merge order.
    """
    if not reports:
        return []

    prs, graph = _build_conflict_graph(reports)
    remaining = set(prs)
    order: list[tuple[int, str]] = []

    while remaining:
        # Pick the PR with the lowest total outgoing weight among remaining.
        # Break ties with the lowest PR number for determinism.
        best = min(remaining, key=lambda p: (_total_weight(p, graph), p))

        reason = _build_reason(best, graph, len(remaining))
        order.append((best, reason))

        remaining.discard(best)
        _remove_pr(best, graph)

    return order


# ── Merge readiness (merge queue integration) ──────────────────────


_SEVERITY_RANK: dict[str, int] = {"critical": 2, "warning": 1, "info": 0}


@dataclass
class MergeReadiness:
    """Whether a PR is ready to merge based on cross-PR conflict analysis."""

    pr_number: int
    is_blocked: bool
    blocking_prs: list[int] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    priority_override: bool = False
    suggested_position: int = 1
    status_description: str = ""

    @property
    def status_state(self) -> str:
        if self.priority_override or not self.is_blocked:
            return "success"
        return "failure"


def compute_merge_readiness(
    pr_number: int,
    reports: list[ConflictReport],
    block_severity: str = "critical",
    priority_labels: dict[str, int] | None = None,
) -> MergeReadiness:
    """Compute whether a PR is ready to merge based on conflict analysis.

    Args:
        pr_number: The PR to check readiness for.
        reports: Conflict reports (can be a single PR's report in a list).
        block_severity: Minimum severity that blocks merging.
        priority_labels: Label → score mapping. Positive total = override blocking.

    Returns:
        MergeReadiness with blocking status and status description.
    """
    if priority_labels is None:
        priority_labels = {}

    # Find the target PR's report
    target_report: ConflictReport | None = None
    for r in reports:
        if r.pr.number == pr_number:
            target_report = r
            break

    if target_report is None:
        return MergeReadiness(
            pr_number=pr_number,
            is_blocked=False,
            status_description="No conflict data — OK to merge",
        )

    # Filter conflicts at or above block_severity
    block_rank = _SEVERITY_RANK.get(block_severity, 2)
    blocking_conflicts = [
        c
        for c in target_report.conflicts
        if _SEVERITY_RANK.get(c.severity.value, 0) >= block_rank
    ]

    # Determine blocking PRs
    blocking_prs = sorted({c.target_pr for c in blocking_conflicts})

    # Check priority labels for override
    priority_score = 0
    for label in target_report.pr.labels:
        priority_score += priority_labels.get(label, 0)
    priority_override = priority_score > 0 and len(blocking_prs) > 0

    # Get merge order position
    order = suggest_merge_order(reports)
    suggested_position = 1
    for pos, (pn, _reason) in enumerate(order, start=1):
        if pn == pr_number:
            suggested_position = pos
            break

    # Determine if blocked — any conflicts at or above severity = blocked
    is_blocked = len(blocking_prs) > 0 and not priority_override

    # Build status description (max 140 chars for GitHub)
    if not blocking_prs:
        desc = "No cross-PR conflicts detected"
    elif priority_override:
        pr_list = ", ".join(f"#{p}" for p in blocking_prs[:5])
        desc = f"Priority override — conflicts with {pr_list}"
    elif is_blocked:
        pr_list = ", ".join(f"#{p}" for p in blocking_prs[:5])
        n = len(blocking_conflicts)
        desc = f"Blocked: {n} conflict(s) with {pr_list}"
        if len(blocking_prs) > 5:
            desc += f" +{len(blocking_prs) - 5} more"
    else:
        desc = f"Position #{suggested_position} in merge order — OK"

    # Truncate to 140
    if len(desc) > 140:
        desc = desc[:137] + "..."

    reasons: list[str] = []
    if blocking_prs:
        reasons.append(f"Conflicts with PRs: {', '.join(f'#{p}' for p in blocking_prs)}")
    if priority_override:
        reasons.append("Priority label override active")

    return MergeReadiness(
        pr_number=pr_number,
        is_blocked=is_blocked,
        blocking_prs=blocking_prs,
        reasons=reasons,
        priority_override=priority_override,
        suggested_position=suggested_position,
        status_description=desc,
    )


def format_merge_order(
    order: list[tuple[int, str]],
    reports: list[ConflictReport],
) -> str:
    """Format merge order as a human-readable string.

    Produces a numbered list with PR title, risk score, and the reason
    it was placed at that position.
    """
    if not order:
        return "No PRs to merge."

    # Index reports by PR number for quick lookup.
    report_map: dict[int, ConflictReport] = {r.pr.number: r for r in reports}

    lines: list[str] = ["Suggested merge order:", ""]

    for position, (pr_number, reason) in enumerate(order, start=1):
        report = report_map.get(pr_number)
        if report:
            title = report.pr.title
            risk = report.risk_score
            severity_counts = report.conflict_count_by_severity
            conflict_summary = ", ".join(
                f"{count} {sev}" for sev, count in sorted(severity_counts.items())
            )
            lines.append(f"  {position}. PR #{pr_number}: {title}")
            lines.append(f"     Risk score: {risk:.1f}")
            if conflict_summary:
                lines.append(f"     Conflicts: {conflict_summary}")
            lines.append(f"     Reason: {reason}")
        else:
            lines.append(f"  {position}. PR #{pr_number}")
            lines.append(f"     Reason: {reason}")

        lines.append("")

    return "\n".join(lines)
