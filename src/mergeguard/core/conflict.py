"""Cross-PR conflict detection engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mergeguard.analysis.similarity import detect_potential_duplications
from mergeguard.models import (
    ChangedSymbol,
    Conflict,
    ConflictSeverity,
    ConflictType,
    PRInfo,
    Symbol,
    SymbolType,
)

logger = logging.getLogger(__name__)

_TEST_DIR_SEGMENTS = {"tests", "test", "__tests__", "spec"}
_TEST_FILE_PATTERNS = ("test_", "_test.", ".test.", ".spec.", "_spec.")


def _is_test_file(path: str) -> bool:
    """Check if a file path looks like a test file.

    Matches common patterns across Python, JS/TS, Go, Ruby, etc.
    """
    # Check directory segments
    parts = path.replace("\\", "/").split("/")
    if any(segment in _TEST_DIR_SEGMENTS for segment in parts[:-1]):
        return True
    # Check filename patterns
    filename = parts[-1] if parts else path
    return any(pattern in filename for pattern in _TEST_FILE_PATTERNS)


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
    logger.debug(
        "Classifying conflicts between PR #%d and PR #%d (%d file overlaps)",
        target_pr.number,
        other_pr.number,
        len(file_overlaps),
    )

    target_cs_map = _build_cs_map(target_pr)
    other_cs_map = _build_cs_map(other_pr)

    for overlap in file_overlaps:
        is_test = _is_test_file(overlap.file_path)

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
                severity = ConflictSeverity.WARNING if is_test else ConflictSeverity.CRITICAL
                for symbol_name in shared_symbols:
                    conflicts.append(
                        Conflict(
                            conflict_type=ConflictType.HARD,
                            severity=severity,
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
                            source_lines=_extract_lines(
                                target_pr,
                                overlap.file_path,
                                symbol_name,
                                target_cs_map,
                            ),
                            target_lines=_extract_lines(
                                other_pr,
                                overlap.file_path,
                                symbol_name,
                                other_cs_map,
                            ),
                        )
                    )
            else:
                severity = ConflictSeverity.INFO if is_test else ConflictSeverity.WARNING
                if is_test:
                    description = (
                        f"Both PRs modify `{overlap.file_path}` "
                        f"at overlapping line ranges. "
                        f"This is common when both PRs append new tests."
                    )
                    recommendation = (
                        "This is typically resolved by rebasing after merge. "
                        "No manual intervention needed."
                    )
                else:
                    description = (
                        f"Both PRs modify `{overlap.file_path}` at overlapping line ranges."
                    )
                    recommendation = (
                        "Review both changes for compatibility. Consider merging one PR first."
                    )
                conflicts.append(
                    Conflict(
                        conflict_type=ConflictType.HARD,
                        severity=severity,
                        source_pr=target_pr.number,
                        target_pr=other_pr.number,
                        file_path=overlap.file_path,
                        description=description,
                        recommendation=recommendation,
                        source_lines=overlap.pr_a_lines[0] if overlap.pr_a_lines else None,
                        target_lines=overlap.pr_b_lines[0] if overlap.pr_b_lines else None,
                    )
                )
        else:
            # Same file, different lines — check for behavioral conflicts
            _check_behavioral_conflict(
                target_pr, other_pr, overlap, conflicts, is_test, target_cs_map, other_cs_map
            )

    # Check for interface conflicts
    _check_interface_conflicts(target_pr, other_pr, conflicts)

    # Check for duplication conflicts
    _check_duplication_conflicts(target_pr, other_pr, conflicts)

    # Check for PR-level duplication (title/description similarity)
    _check_pr_duplication(target_pr, other_pr, file_overlaps, conflicts)

    # Populate diff previews for all conflicts
    for conflict in conflicts:
        if conflict.source_diff_preview is None:
            conflict.source_diff_preview = _get_symbol_diff_preview(
                target_pr, conflict.file_path, conflict.symbol_name
            )
        if conflict.target_diff_preview is None:
            conflict.target_diff_preview = _get_symbol_diff_preview(
                other_pr, conflict.file_path, conflict.symbol_name
            )

    return conflicts


_COMMENT_PATTERNS: dict[str, list[str]] = {
    ".py": ["#", '"""', "'''"],
    ".js": ["//", "/*", "*", "*/"],
    ".ts": ["//", "/*", "*", "*/"],
    ".go": ["//", "/*", "*", "*/"],
    ".java": ["//", "/*", "*", "*/"],
    ".rb": ["#"],
    ".rs": ["//", "/*", "*", "*/"],
}


def _is_comment_only_change(raw_diff: str | None, file_path: str) -> bool:
    """Check if a diff contains only comment/docstring changes."""
    if not raw_diff:
        return False
    ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
    prefixes = _COMMENT_PATTERNS.get(ext, [])
    if not prefixes:
        return False
    for line in raw_diff.splitlines():
        content = line[1:].strip()  # Remove +/- prefix
        if not content:
            continue  # blank lines are fine
        if not any(content.startswith(p) for p in prefixes):
            return False
    return True


def _build_cs_map(pr: PRInfo) -> dict[tuple[str, str], ChangedSymbol]:
    """Build a (file_path, symbol_name) → ChangedSymbol lookup dict."""
    return {(cs.symbol.file_path, cs.symbol.name): cs for cs in pr.changed_symbols}


def _extract_lines(
    pr: PRInfo,
    file_path: str,
    symbol_name: str | None,
    cs_map: dict[tuple[str, str], ChangedSymbol] | None = None,
    overlap_lines: list[tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    """Extract line range for a conflict from symbol or overlap data."""
    if symbol_name:
        cs = _find_changed_symbol(pr, file_path, symbol_name, cs_map)
        if cs:
            return cs.diff_lines
    if overlap_lines:
        return overlap_lines[0]
    return None


def _find_changed_symbol(
    pr: PRInfo,
    file_path: str,
    symbol_name: str,
    cs_map: dict[tuple[str, str], ChangedSymbol] | None = None,
) -> ChangedSymbol | None:
    """Find a ChangedSymbol object by name in a PR's changed_symbols."""
    if cs_map is not None:
        return cs_map.get((file_path, symbol_name))
    for cs in pr.changed_symbols:
        if cs.symbol.file_path == file_path and cs.symbol.name == symbol_name:
            return cs
    return None


def _check_behavioral_conflict(
    target_pr: PRInfo,
    other_pr: PRInfo,
    overlap: FileOverlap,
    conflicts: list[Conflict],
    is_test: bool = False,
    target_cs_map: dict[tuple[str, str], ChangedSymbol] | None = None,
    other_cs_map: dict[tuple[str, str], ChangedSymbol] | None = None,
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

    base_severity = ConflictSeverity.INFO if is_test else ConflictSeverity.WARNING
    for symbol_name in shared_symbols:
        # Check if both sides are comment-only changes
        target_cs = _find_changed_symbol(target_pr, overlap.file_path, symbol_name, target_cs_map)
        other_cs = _find_changed_symbol(other_pr, overlap.file_path, symbol_name, other_cs_map)
        if (
            target_cs
            and other_cs
            and _is_comment_only_change(target_cs.raw_diff, overlap.file_path)
            and _is_comment_only_change(other_cs.raw_diff, overlap.file_path)
        ):
            continue  # Both sides are comment-only, skip

        severity = base_severity
        is_class = target_cs and target_cs.symbol.symbol_type == SymbolType.CLASS
        if is_class:
            severity = ConflictSeverity.INFO  # Class-level: method conflicts capture real risk
        elif (
            severity == ConflictSeverity.WARNING
            and target_cs
            and target_cs.symbol.parent
            and target_cs.symbol.parent in shared_symbols
        ):
            # Demote methods whose parent class is also a shared symbol —
            # the class-level conflict already covers this risk.
            severity = ConflictSeverity.INFO

        conflicts.append(
            Conflict(
                conflict_type=ConflictType.BEHAVIORAL,
                severity=severity,
                source_pr=target_pr.number,
                target_pr=other_pr.number,
                file_path=overlap.file_path,
                symbol_name=symbol_name,
                description=(
                    f"Both PRs modify `{symbol_name}` in "
                    f"`{overlap.file_path}` at different lines. "
                    f"Changes may interact unexpectedly."
                ),
                recommendation=("Review both changes to ensure they are semantically compatible."),
                source_lines=_extract_lines(
                    target_pr,
                    overlap.file_path,
                    symbol_name,
                    target_cs_map,
                ),
                target_lines=_extract_lines(
                    other_pr,
                    overlap.file_path,
                    symbol_name,
                    other_cs_map,
                ),
            )
        )

    # Check for caller/callee relationships between different modified symbols
    target_only = target_symbols - other_symbols
    other_only = other_symbols - target_symbols

    seen_pairs: set[tuple[str, str]] = set()
    for t_name in target_only:
        t_sym = _find_symbol(target_pr, overlap.file_path, t_name, target_cs_map)
        if not t_sym:
            continue
        for o_name in other_only:
            o_sym = _find_symbol(other_pr, overlap.file_path, o_name, other_cs_map)
            if not o_sym:
                continue
            # Check if either calls the other
            t_calls_o = o_name in t_sym.dependencies
            o_calls_t = t_name in o_sym.dependencies
            if t_calls_o or o_calls_t:
                caller, callee = (t_name, o_name) if t_calls_o else (o_name, t_name)
                pair_key = (min(caller, callee), max(caller, callee))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                cc_severity = ConflictSeverity.INFO if is_test else ConflictSeverity.WARNING

                # Demote to INFO if the callee's signature hasn't changed.
                # Stable interface = low interaction risk.
                if cc_severity == ConflictSeverity.WARNING:
                    if t_calls_o:
                        callee_cs = _find_changed_symbol(
                            other_pr, overlap.file_path, callee, other_cs_map
                        )
                    else:
                        callee_cs = _find_changed_symbol(
                            target_pr, overlap.file_path, callee, target_cs_map
                        )
                    if callee_cs and callee_cs.change_type != "modified_signature":
                        cc_severity = ConflictSeverity.INFO

                conflicts.append(
                    Conflict(
                        conflict_type=ConflictType.BEHAVIORAL,
                        severity=cc_severity,
                        source_pr=target_pr.number,
                        target_pr=other_pr.number,
                        file_path=overlap.file_path,
                        symbol_name=f"{caller} \u2192 {callee}",
                        description=(
                            f"`{caller}` calls `{callee}` in `{overlap.file_path}`. "
                            f"PR #{target_pr.number} modifies one while "
                            f"PR #{other_pr.number} modifies the other. "
                            f"Changes may interact unexpectedly."
                        ),
                        recommendation=(
                            "Test both changes together before merging. "
                            "The caller/callee relationship means changes "
                            "in one function may affect the other's behavior."
                        ),
                    )
                )


def _find_symbol(
    pr: PRInfo,
    file_path: str,
    symbol_name: str,
    cs_map: dict[tuple[str, str], ChangedSymbol] | None = None,
) -> Symbol | None:
    """Find a Symbol object by name in a PR's changed_symbols."""
    if cs_map is not None:
        cs = cs_map.get((file_path, symbol_name))
        return cs.symbol if cs else None
    for cs in pr.changed_symbols:
        if cs.symbol.file_path == file_path and cs.symbol.name == symbol_name:
            return cs.symbol
    return None


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
                            source_lines=(cs.symbol.start_line, cs.symbol.end_line),
                            target_lines=(other_cs.symbol.start_line, other_cs.symbol.end_line),
                        )
                    )


def _check_duplication_conflicts(
    target_pr: PRInfo,
    other_pr: PRInfo,
    conflicts: list[Conflict],
) -> None:
    """Detect duplicate symbols added by both PRs independently."""
    # Collect newly added/modified symbols from each PR
    target_symbols = [cs.symbol for cs in target_pr.changed_symbols]
    other_symbols = [cs.symbol for cs in other_pr.changed_symbols]

    if not target_symbols or not other_symbols:
        return

    # Build change_type lookups to filter out modify-modify pairs
    target_ct = {
        (cs.symbol.file_path, cs.symbol.name): cs.change_type for cs in target_pr.changed_symbols
    }
    other_ct = {
        (cs.symbol.file_path, cs.symbol.name): cs.change_type for cs in other_pr.changed_symbols
    }
    _modify = {"modified_body", "modified_signature"}

    duplications = detect_potential_duplications(target_symbols, other_symbols)
    seen_pairs: set[tuple[str, str]] = set()
    for new_sym, other_sym, score in duplications:
        # Skip same-file same-name — already caught by behavioral/hard
        if new_sym.file_path == other_sym.file_path and new_sym.name == other_sym.name:
            continue
        # Skip when both sides modify existing code (not new additions)
        if (
            target_ct.get((new_sym.file_path, new_sym.name)) in _modify
            and other_ct.get((other_sym.file_path, other_sym.name)) in _modify
        ):
            continue
        pair_key = (new_sym.name, other_sym.name)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        conflicts.append(
            Conflict(
                conflict_type=ConflictType.DUPLICATION,
                severity=ConflictSeverity.INFO,
                source_pr=target_pr.number,
                target_pr=other_pr.number,
                file_path=new_sym.file_path,
                symbol_name=new_sym.name,
                description=(
                    f"`{new_sym.name}` in PR #{target_pr.number} is similar "
                    f"to `{other_sym.name}` in PR #{other_pr.number} "
                    f"(similarity: {score:.0%}). Possible duplication."
                ),
                recommendation=(
                    "Review both PRs for duplicated functionality. "
                    "Consider consolidating into one implementation."
                ),
                source_lines=(new_sym.start_line, new_sym.end_line),
                target_lines=(other_sym.start_line, other_sym.end_line),
            )
        )


def _quick_token_similarity(a: str, b: str) -> float:
    """Fast Jaccard similarity on word tokens."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _check_pr_duplication(
    target_pr: PRInfo,
    other_pr: PRInfo,
    file_overlaps: list[FileOverlap],
    conflicts: list[Conflict],
) -> None:
    """Detect PRs that may be duplicate efforts based on title/description similarity."""
    from difflib import SequenceMatcher

    # Must share at least one file
    if not file_overlaps:
        return

    # Fast pre-filter: skip SequenceMatcher if titles are very dissimilar
    if _quick_token_similarity(target_pr.title, other_pr.title) < 0.15:
        return

    # Title similarity
    title_sim = SequenceMatcher(None, target_pr.title.lower(), other_pr.title.lower()).ratio()

    # Description similarity (if both have descriptions)
    desc_sim = 0.0
    if target_pr.description and other_pr.description:
        desc_sim = SequenceMatcher(
            None,
            target_pr.description.lower()[:500],
            other_pr.description.lower()[:500],
        ).ratio()

    # Combined score: title weighted more heavily
    combined = title_sim * 0.6 + desc_sim * 0.4
    file_overlap_ratio = len(file_overlaps) / max(
        len(target_pr.changed_files), len(other_pr.changed_files), 1
    )

    # Trigger if high text similarity AND significant file overlap
    if combined >= 0.5 and file_overlap_ratio >= 0.3:
        conflicts.append(
            Conflict(
                conflict_type=ConflictType.DUPLICATION,
                severity=ConflictSeverity.WARNING,
                source_pr=target_pr.number,
                target_pr=other_pr.number,
                file_path=file_overlaps[0].file_path,
                description=(
                    f"PR #{other_pr.number} ({other_pr.title!r}) may be a "
                    f"duplicate effort. Title similarity: {title_sim:.0%}, "
                    f"file overlap: {len(file_overlaps)} shared file(s)."
                ),
                recommendation=(
                    "Review both PRs for overlapping intent. "
                    "If they solve the same problem, close one "
                    "or merge the approaches."
                ),
            )
        )


def _get_symbol_diff_preview(pr: PRInfo, file_path: str, symbol_name: str | None) -> str | None:
    """Extract a diff preview for a symbol in a PR, truncated for display."""
    if symbol_name is None:
        # File-level: use first 10 lines of patch
        for cf in pr.changed_files:
            if cf.path == file_path and cf.patch:
                lines = cf.patch.splitlines()[:10]
                preview = "\n".join(lines)
                if len(cf.patch.splitlines()) > 10:
                    preview += "\n..."
                return preview
        return None
    # Symbol-level: find the matching ChangedSymbol's raw_diff
    for cs in pr.changed_symbols:
        if cs.symbol.file_path == file_path and cs.symbol.name == symbol_name and cs.raw_diff:
            lines = cs.raw_diff.splitlines()[:10]
            preview = "\n".join(lines)
            if len(cs.raw_diff.splitlines()) > 10:
                preview += "\n..."
            return preview
    return None


def _get_modified_ranges(pr: PRInfo, file_path: str) -> list[tuple[int, int]]:
    """Extract modified line ranges for a specific file in a PR."""
    ranges = [cs.diff_lines for cs in pr.changed_symbols if cs.symbol.file_path == file_path]
    if ranges:
        return ranges
    # Fallback: use the raw diff data from changed_files
    for cf in pr.changed_files:
        if cf.path == file_path and cf.patch:
            from mergeguard.analysis.diff_parser import parse_unified_diff

            file_diffs = parse_unified_diff(f"diff --git a/{cf.path} b/{cf.path}\n{cf.patch}")
            if file_diffs:
                return file_diffs[0].all_modified_line_ranges
    return []
