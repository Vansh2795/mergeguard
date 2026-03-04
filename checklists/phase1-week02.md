# Phase 1 — Week 2: Diff Parser + File Overlap Matrix

## Goals
- Parse unified diffs into structured data
- Detect which PRs touch the same files

## Daily Tasks

### Day 1-3: Diff Parser
- [x] Implement `parse_unified_diff()` in diff_parser.py
- [x] Handle multi-file diffs
- [x] Handle new/deleted file markers
- [x] Handle file renames
- [x] Extract added/removed line ranges per hunk
- [x] Create `FileDiff` and `DiffHunk` dataclasses
- [x] Write comprehensive tests with edge cases

### Day 4-5: File Overlap Matrix
- [x] Implement `compute_file_overlaps()` in conflict.py
- [x] Create `FileOverlap` dataclass with line-range overlap detection
- [x] Implement `has_line_overlap` property
- [x] Write tests with known overlapping and non-overlapping PRs

## Deliverables
- [x] Diff parser that handles all standard git diff formats
- [x] File overlap detection between any pair of PRs
- [x] 90%+ test coverage on diff_parser.py

## Acceptance Criteria
- [x] parse_unified_diff correctly handles: modifications, additions, deletions, renames
- [x] FileOverlap.has_line_overlap correctly detects overlapping line ranges
- [x] All tests pass with fixture diffs
