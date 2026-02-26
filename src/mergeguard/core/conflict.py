"""Cross-PR conflict detection engine."""

from __future__ import annotations

from dataclasses import dataclass

from mergeguard.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    PRInfo,
)


@dataclass
class FileOverlap:
    """Two PRs that modify the same file."""

    file_path: str
    pr_a: int
    pr_b: int
    pr_a_lines: list[tuple[int, int]]  # Modified line ranges in PR A
    pr_b_lines: list[tuple[int, int]]  # Modified line ranges in PR B

    @property
    def has_line_overlap(self) -> bool:
        """Check if the actual modified lines overlap (hard conflict)."""
        for a_start, a_end in self.pr_a_lines:
            for b_start, b_end in self.pr_b_lines:
                if a_start <= b_end and b_start <= a_end:
                    return True
        return False


def compute_file_overlaps(
    target_pr: PRInfo, other_prs: list[PRInfo]
) -> dict[int, list[FileOverlap]]:
    """Find all files that target_pr shares with each other open PR.

    Returns a dict mapping other_pr.number -> list of FileOverlap.
    PRs with no overlapping files are omitted.
    """
    target_files = target_pr.file_paths
    overlaps: dict[int, list[FileOverlap]] = {}

    for other in other_prs:
        if other.number == target_pr.number:
            continue

        shared_files = target_files & other.file_paths
        if not shared_files:
            continue

        file_overlaps: list[FileOverlap] = []
        for path in shared_files:
            # Get modified line ranges for both PRs
            target_ranges = _get_modified_ranges(target_pr, path)
            other_ranges = _get_modified_ranges(other, path)

            file_overlaps.append(
                FileOverlap(
                    file_path=path,
                    pr_a=target_pr.number,
                    pr_b=other.number,
                    pr_a_lines=target_ranges,
                    pr_b_lines=other_ranges,
                )
            )

        if file_overlaps:
            overlaps[other.number] = file_overlaps

    return overlaps


def classify_conflicts(
    target_pr: PRInfo,
    other_pr: PRInfo,
    file_overlaps: list[FileOverlap],
) -> list[Conflict]:
    """Classify conflicts between two PRs based on their file overlaps.

    Implements the conflict classification algorithm:
    1. Hard conflicts: same lines modified
    2. Interface conflicts: signature changed, callers not updated
    3. Behavioral conflicts: same function, different lines
    4. Duplication: similar new symbols added
    """
    conflicts: list[Conflict] = []

    for overlap in file_overlaps:
        # Check for hard conflicts (same lines modified)
        if overlap.has_line_overlap:
            # Find which symbols overlap
            target_symbols = {
                cs.symbol.name
                for cs in target_pr.changed_symbols
                if cs.symbol.file_path == overlap.file_path
            }
            other_symbols = {
                cs.symbol.name
                for cs in other_pr.changed_symbols
                if cs.symbol.file_path == overlap.file_path
            }
            shared_symbols = target_symbols & other_symbols

            if shared_symbols:
                for symbol_name in shared_symbols:
                    conflicts.append(
                        Conflict(
                            conflict_type=ConflictType.HARD,
                            severity=ConflictSeverity.CRITICAL,
                            source_pr=target_pr.number,
                            target_pr=other_pr.number,
                            file_path=overlap.file_path,
                            symbol_name=symbol_name,
                            description=(
                                f"Both PRs modify `{symbol_name}` in "
                                f"`{overlap.file_path}` at overlapping lines."
                            ),
                            recommendation=(
                                "Coordinate with the other PR author. "
                                "One PR should merge first, then the other "
                                "should rebase and resolve conflicts."
                            ),
                        )
                    )
            else:
                conflicts.append(
                    Conflict(
                        conflict_type=ConflictType.HARD,
                        severity=ConflictSeverity.WARNING,
                        source_pr=target_pr.number,
                        target_pr=other_pr.number,
                        file_path=overlap.file_path,
                        description=(
                            f"Both PRs modify `{overlap.file_path}` "
                            f"at overlapping line ranges."
                        ),
                        recommendation=(
                            "Review both changes for compatibility. "
                            "Consider merging one PR first."
                        ),
                    )
                )
        else:
            # Same file, different lines — check for behavioral conflicts
            _check_behavioral_conflict(target_pr, other_pr, overlap, conflicts)

    # Check for interface conflicts
    _check_interface_conflicts(target_pr, other_pr, conflicts)

    return conflicts


def _check_behavioral_conflict(
    target_pr: PRInfo,
    other_pr: PRInfo,
    overlap: FileOverlap,
    conflicts: list[Conflict],
) -> None:
    """Check for behavioral conflicts: same function modified at different lines."""
    target_symbols = {
        cs.symbol.name
        for cs in target_pr.changed_symbols
        if cs.symbol.file_path == overlap.file_path
    }
    other_symbols = {
        cs.symbol.name
        for cs in other_pr.changed_symbols
        if cs.symbol.file_path == overlap.file_path
    }
    shared_symbols = target_symbols & other_symbols

    for symbol_name in shared_symbols:
        conflicts.append(
            Conflict(
                conflict_type=ConflictType.BEHAVIORAL,
                severity=ConflictSeverity.WARNING,
                source_pr=target_pr.number,
                target_pr=other_pr.number,
                file_path=overlap.file_path,
                symbol_name=symbol_name,
                description=(
                    f"Both PRs modify `{symbol_name}` in "
                    f"`{overlap.file_path}` at different lines. "
                    f"Changes may interact unexpectedly."
                ),
                recommendation=(
                    "Review both changes to ensure they are "
                    "semantically compatible."
                ),
            )
        )


def _check_interface_conflicts(
    target_pr: PRInfo,
    other_pr: PRInfo,
    conflicts: list[Conflict],
) -> None:
    """Check for interface conflicts: signature changes affecting callers."""
    # Find signature changes in target PR
    for cs in target_pr.changed_symbols:
        if cs.change_type == "modified_signature":
            # Check if any of the other PR's changes reference this symbol
            for other_cs in other_pr.changed_symbols:
                if cs.symbol.name in other_cs.symbol.dependencies:
                    conflicts.append(
                        Conflict(
                            conflict_type=ConflictType.INTERFACE,
                            severity=ConflictSeverity.CRITICAL,
                            source_pr=target_pr.number,
                            target_pr=other_pr.number,
                            file_path=cs.symbol.file_path,
                            symbol_name=cs.symbol.name,
                            description=(
                                f"This PR changes the signature of "
                                f"`{cs.symbol.name}`, but PR "
                                f"#{other_pr.number} calls it with "
                                f"the old signature."
                            ),
                            recommendation=(
                                "Update the caller in the other PR "
                                "to match the new signature, or "
                                "merge this PR first and rebase."
                            ),
                        )
                    )


def _get_modified_ranges(pr: PRInfo, file_path: str) -> list[tuple[int, int]]:
    """Extract modified line ranges for a specific file in a PR."""
    for cs in pr.changed_symbols:
        if cs.symbol.file_path == file_path:
            return [cs.diff_lines]
    # Fallback: use the raw diff data from changed_files
    for cf in pr.changed_files:
        if cf.path == file_path and cf.patch:
            from mergeguard.analysis.diff_parser import parse_unified_diff

            file_diffs = parse_unified_diff(
                f"diff --git a/{cf.path} b/{cf.path}\n{cf.patch}"
            )
            if file_diffs:
                return file_diffs[0].all_modified_line_ranges
    return []
