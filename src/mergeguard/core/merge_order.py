"""Suggest optimal merge order based on inter-PR conflict graph.

Builds a weighted conflict graph from ConflictReport objects and greedily
selects the PR with the lowest total outgoing conflict weight at each step.
After each selection, edges for the merged PR are removed and weights
recalculated for the remaining nodes.
"""

from __future__ import annotations

from collections import defaultdict

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
