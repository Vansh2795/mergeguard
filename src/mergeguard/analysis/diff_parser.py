"""Parse unified diffs into structured representations."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DiffHunk:
    """A single hunk within a file diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_lines: list[tuple[int, str]]  # (line_number, content)
    removed_lines: list[tuple[int, str]]  # (line_number, content)
    context_lines: list[tuple[int, str]]  # (line_number, content)


@dataclass
class FileDiff:
    """Parsed diff for a single file."""

    path: str
    old_path: str | None  # For renames
    hunks: list[DiffHunk]
    is_new: bool = False
    is_deleted: bool = False

    @property
    def all_modified_line_ranges(self) -> list[tuple[int, int]]:
        """Get all line ranges that were modified (in the new file)."""
        ranges: list[tuple[int, int]] = []
        for hunk in self.hunks:
            if hunk.added_lines:
                start = min(ln for ln, _ in hunk.added_lines)
                end = max(ln for ln, _ in hunk.added_lines)
                ranges.append((start, end))
        return ranges


# Regex patterns
DIFF_HEADER = re.compile(r"^diff --git a/(.*) b/(.*)$")
HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """Parse a full unified diff into structured FileDiff objects.

    This handles the standard `git diff` output format, including
    multi-file diffs with rename detection.
    """
    files: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk: DiffHunk | None = None
    new_line_num = 0
    old_line_num = 0

    for line in diff_text.split("\n"):
        # New file header
        header_match = DIFF_HEADER.match(line)
        if header_match:
            if current_file and current_hunk:
                current_file.hunks.append(current_hunk)
            if current_file:
                files.append(current_file)

            old_path = header_match.group(1)
            new_path = header_match.group(2)
            current_file = FileDiff(
                path=new_path,
                old_path=old_path if old_path != new_path else None,
                hunks=[],
            )
            current_hunk = None
            continue

        if current_file is None:
            continue

        # Check for new/deleted file markers
        if line.startswith("new file"):
            current_file.is_new = True
            continue
        if line.startswith("deleted file"):
            current_file.is_deleted = True
            continue

        # Hunk header
        hunk_match = HUNK_HEADER.match(line)
        if hunk_match:
            if current_hunk:
                current_file.hunks.append(current_hunk)

            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2) or "1")
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4) or "1")

            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                added_lines=[],
                removed_lines=[],
                context_lines=[],
            )
            new_line_num = new_start
            old_line_num = old_start
            continue

        if current_hunk is None:
            continue

        # Diff content lines
        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.added_lines.append((new_line_num, line[1:]))
            new_line_num += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.removed_lines.append((old_line_num, line[1:]))
            old_line_num += 1
        elif line.startswith(" "):
            current_hunk.context_lines.append((new_line_num, line[1:]))
            new_line_num += 1
            old_line_num += 1

    # Don't forget the last file/hunk
    if current_file and current_hunk:
        current_file.hunks.append(current_hunk)
    if current_file:
        files.append(current_file)

    return files
