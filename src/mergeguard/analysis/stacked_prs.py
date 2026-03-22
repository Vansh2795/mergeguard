"""Stacked PR detection — identifies PR dependency chains.

Supports three detection strategies:
1. Branch chain: follows head_branch → base_branch links between PRs
2. Labels: groups PRs by matching label patterns (e.g., "stack:auth")
3. Graphite metadata: parses Graphite-base trailers in PR descriptions
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from mergeguard.models import PRInfo, StackedPRConfig, StackGroup

logger = logging.getLogger(__name__)

_DEFAULT_BRANCHES = {"main", "master", "develop"}
_MAX_CHAIN_LENGTH = 20


def detect_stacks(prs: list[PRInfo], config: StackedPRConfig) -> list[StackGroup]:
    """Detect stacked PR groups using configured strategies.

    Returns deduplicated groups ordered by detection priority:
    branch_chain > graphite > labels.
    """
    if not prs or not config.enabled:
        return []

    all_groups: dict[str, list[StackGroup]] = {}

    for method in config.detection:
        if method == "branch_chain":
            all_groups["branch_chain"] = _detect_branch_chains(prs)
        elif method == "labels":
            all_groups["labels"] = _detect_by_labels(prs, config.label_pattern)
        elif method == "graphite":
            all_groups["graphite"] = _detect_graphite(prs)
        else:
            logger.warning("Unknown stacked PR detection method: %s", method)

    return _deduplicate_groups(all_groups)


def build_stack_lookup(groups: list[StackGroup]) -> dict[int, StackGroup]:
    """Build a PR number → StackGroup lookup from a list of groups."""
    lookup: dict[int, StackGroup] = {}
    for group in groups:
        for pr_num in group.pr_numbers:
            lookup[pr_num] = group
    return lookup


# ── Strategy 1: Branch chain ──────────────────────────────────────────


def _detect_branch_chains(prs: list[PRInfo]) -> list[StackGroup]:
    """Detect stacks by following head_branch → base_branch links.

    A stack root is a PR whose base_branch is a default branch AND whose
    head_branch is used as another PR's base_branch.
    """
    # Build head_branch → PR map
    head_to_pr: dict[str, list[PRInfo]] = defaultdict(list)
    for pr in prs:
        head_to_pr[pr.head_branch].append(pr)

    # Build base_branch → PRs that target it
    base_to_prs: dict[str, list[PRInfo]] = defaultdict(list)
    for pr in prs:
        base_to_prs[pr.base_branch].append(pr)

    groups: list[StackGroup] = []
    visited_prs: set[int] = set()

    # Find roots: PRs targeting a default branch whose head is another PR's base
    roots: list[PRInfo] = []
    for pr in prs:
        if pr.base_branch in _DEFAULT_BRANCHES and pr.head_branch in base_to_prs:
            # Check that at least one PR actually targets this head_branch
            children = [p for p in base_to_prs[pr.head_branch] if p.number != pr.number]
            if children:
                roots.append(pr)

    # Sort roots by created_at for determinism
    roots.sort(key=lambda p: (p.created_at, p.number))

    for root in roots:
        if root.number in visited_prs:
            continue

        chain = _walk_chain(root, base_to_prs, head_to_pr, visited_prs)
        if len(chain) < 2:
            continue

        pr_numbers = [pr.number for pr in chain]
        is_complete = _check_chain_completeness(chain, base_to_prs)

        groups.append(
            StackGroup(
                group_id=f"chain-{root.head_branch}",
                pr_numbers=pr_numbers,
                base_branch=root.base_branch,
                detection_method="branch_chain",
                is_complete=is_complete,
            )
        )

    return groups


def _walk_chain(
    root: PRInfo,
    base_to_prs: dict[str, list[PRInfo]],
    head_to_pr: dict[str, list[PRInfo]],
    visited: set[int],
) -> list[PRInfo]:
    """Walk a branch chain from root to tip, following head→base links."""
    chain: list[PRInfo] = [root]
    visited.add(root.number)
    current = root

    for _ in range(_MAX_CHAIN_LENGTH):
        # Find PRs whose base_branch == current.head_branch
        children = [
            p for p in base_to_prs.get(current.head_branch, [])
            if p.number != current.number and p.number not in visited
        ]

        if not children:
            break

        # If multiple PRs target the same base, pick oldest (fork scenario)
        children.sort(key=lambda p: (p.created_at, p.number))
        next_pr = children[0]

        if next_pr.number in visited:
            logger.warning(
                "Circular reference detected in stack at PR #%d", next_pr.number
            )
            break

        visited.add(next_pr.number)
        chain.append(next_pr)
        current = next_pr

    return chain


def _check_chain_completeness(
    chain: list[PRInfo],
    base_to_prs: dict[str, list[PRInfo]],
) -> bool:
    """Check if all intermediate links in the chain are present."""
    return all(chain[i].base_branch == chain[i - 1].head_branch for i in range(1, len(chain)))


# ── Strategy 2: Labels ────────────────────────────────────────────────


def _detect_by_labels(prs: list[PRInfo], label_pattern: str) -> list[StackGroup]:
    """Group PRs by labels matching the configured pattern (e.g., 'stack:auth')."""
    label_groups: dict[str, list[PRInfo]] = defaultdict(list)

    for pr in prs:
        for label in pr.labels:
            if label.startswith(label_pattern):
                value = label[len(label_pattern):]
                if value:
                    label_groups[value].append(pr)

    groups: list[StackGroup] = []
    for value, group_prs in label_groups.items():
        if len(group_prs) < 2:
            continue

        # Order by created_at
        group_prs.sort(key=lambda p: (p.created_at, p.number))
        base = group_prs[0].base_branch

        groups.append(
            StackGroup(
                group_id=f"label-{value}",
                pr_numbers=[pr.number for pr in group_prs],
                base_branch=base,
                detection_method="labels",
            )
        )

    return groups


# ── Strategy 3: Graphite metadata ─────────────────────────────────────

_GRAPHITE_BASE_RE = re.compile(r"Graphite-base:\s*(.+)", re.IGNORECASE)


def _detect_graphite(prs: list[PRInfo]) -> list[StackGroup]:
    """Detect stacks from Graphite-base trailers in PR descriptions."""
    # Build parent→children map from Graphite metadata
    parent_map: dict[int, str] = {}  # PR number → parent branch name

    for pr in prs:
        match = _GRAPHITE_BASE_RE.search(pr.description)
        if match:
            parent_map[pr.number] = match.group(1).strip()

    if not parent_map:
        return []

    # Build child map: parent_branch → [child PRs]
    children_of: dict[str, list[PRInfo]] = defaultdict(list)
    for pr in prs:
        parent_branch = parent_map.get(pr.number)
        if parent_branch:
            children_of[parent_branch].append(pr)

    # Find roots: PRs whose graphite parent is a default branch
    # OR PRs whose graphite parent is another PR's head_branch
    visited: set[int] = set()
    groups: list[StackGroup] = []

    # Walk chains from default-branch roots
    for parent_branch in sorted(children_of.keys()):
        if parent_branch not in _DEFAULT_BRANCHES:
            continue

        for root_pr in sorted(children_of[parent_branch], key=lambda p: (p.created_at, p.number)):
            if root_pr.number in visited:
                continue

            chain = _walk_graphite_chain(root_pr, children_of, visited)
            if len(chain) < 2:
                continue

            groups.append(
                StackGroup(
                    group_id=f"graphite-{root_pr.head_branch}",
                    pr_numbers=[pr.number for pr in chain],
                    base_branch=parent_branch,
                    detection_method="graphite",
                )
            )

    return groups


def _walk_graphite_chain(
    root: PRInfo,
    children_of: dict[str, list[PRInfo]],
    visited: set[int],
) -> list[PRInfo]:
    """Walk a Graphite chain from root to tip."""
    chain: list[PRInfo] = [root]
    visited.add(root.number)
    current = root

    for _ in range(_MAX_CHAIN_LENGTH):
        children = [
            p for p in children_of.get(current.head_branch, [])
            if p.number not in visited
        ]
        if not children:
            break

        children.sort(key=lambda p: (p.created_at, p.number))
        next_pr = children[0]
        visited.add(next_pr.number)
        chain.append(next_pr)
        current = next_pr

    return chain


# ── Deduplication ─────────────────────────────────────────────────────

_PRIORITY = {"branch_chain": 0, "graphite": 1, "labels": 2}


def _deduplicate_groups(
    all_groups: dict[str, list[StackGroup]],
) -> list[StackGroup]:
    """Deduplicate groups by priority: branch_chain > graphite > labels.

    If a PR appears in multiple groups, keep only the highest-priority one.
    """
    # Flatten and sort by priority
    flat: list[StackGroup] = []
    for groups in all_groups.values():
        flat.extend(groups)

    flat.sort(key=lambda g: _PRIORITY.get(g.detection_method, 99))

    claimed: set[int] = set()
    result: list[StackGroup] = []

    for group in flat:
        # Check if any PR in this group is already claimed
        overlap = claimed & set(group.pr_numbers)
        if overlap:
            # Remove claimed PRs from this group
            remaining = [n for n in group.pr_numbers if n not in claimed]
            if len(remaining) < 2:
                continue
            group = StackGroup(
                group_id=group.group_id,
                pr_numbers=remaining,
                base_branch=group.base_branch,
                detection_method=group.detection_method,
                is_complete=False,
            )

        claimed.update(group.pr_numbers)
        result.append(group)

    return result
