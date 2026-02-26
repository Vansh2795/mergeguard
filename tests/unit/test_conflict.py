"""Tests for conflict detection module."""
from __future__ import annotations
import pytest
from mergeguard.core.conflict import compute_file_overlaps, classify_conflicts, FileOverlap
from mergeguard.models import (
    PRInfo, ChangedFile, ChangedSymbol, Symbol,
    FileChangeStatus, SymbolType, ConflictType, ConflictSeverity,
)
from datetime import datetime


def make_pr(number, files, symbols=None):
    pr = PRInfo(
        number=number, title=f"PR {number}", author="dev",
        base_branch="main", head_branch=f"branch-{number}",
        head_sha=f"sha{number}", created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    pr.changed_files = [
        ChangedFile(path=f, status=FileChangeStatus.MODIFIED) for f in files
    ]
    pr.changed_symbols = symbols or []
    return pr


class TestComputeFileOverlaps:
    def test_no_overlap(self):
        pr_a = make_pr(1, ["a.py", "b.py"])
        pr_b = make_pr(2, ["c.py", "d.py"])
        overlaps = compute_file_overlaps(pr_a, [pr_b])
        assert len(overlaps) == 0

    def test_single_file_overlap(self):
        pr_a = make_pr(1, ["a.py", "shared.py"])
        pr_b = make_pr(2, ["shared.py", "c.py"])
        overlaps = compute_file_overlaps(pr_a, [pr_b])
        assert 2 in overlaps
        assert len(overlaps[2]) == 1
        assert overlaps[2][0].file_path == "shared.py"

    def test_skip_same_pr(self):
        pr = make_pr(1, ["a.py"])
        overlaps = compute_file_overlaps(pr, [pr])
        assert len(overlaps) == 0

    def test_multiple_overlaps(self):
        pr_a = make_pr(1, ["a.py", "b.py", "c.py"])
        pr_b = make_pr(2, ["a.py", "b.py", "d.py"])
        overlaps = compute_file_overlaps(pr_a, [pr_b])
        assert len(overlaps[2]) == 2


class TestFileOverlap:
    def test_has_line_overlap_true(self):
        overlap = FileOverlap(
            file_path="f.py", pr_a=1, pr_b=2,
            pr_a_lines=[(10, 20)], pr_b_lines=[(15, 25)],
        )
        assert overlap.has_line_overlap is True

    def test_has_line_overlap_false(self):
        overlap = FileOverlap(
            file_path="f.py", pr_a=1, pr_b=2,
            pr_a_lines=[(10, 20)], pr_b_lines=[(25, 35)],
        )
        assert overlap.has_line_overlap is False

    def test_has_line_overlap_adjacent(self):
        overlap = FileOverlap(
            file_path="f.py", pr_a=1, pr_b=2,
            pr_a_lines=[(10, 20)], pr_b_lines=[(20, 25)],
        )
        assert overlap.has_line_overlap is True
