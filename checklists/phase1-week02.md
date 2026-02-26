# Phase 1 — Week 2: Diff Parser + File Overlap Matrix

## Goals
- Parse unified diffs into structured data
- Detect which PRs touch the same files

## Daily Tasks

### Day 1-3: Diff Parser
- [ ] Implement `parse_unified_diff()` in diff_parser.py
- [ ] Handle multi-file diffs
- [ ] Handle new/deleted file markers
- [ ] Handle file renames
- [ ] Extract added/removed line ranges per hunk
- [ ] Create `FileDiff` and `DiffHunk` dataclasses
- [ ] Write comprehensive tests with edge cases

### Day 4-5: File Overlap Matrix
- [ ] Implement `compute_file_overlaps()` in conflict.py
- [ ] Create `FileOverlap` dataclass with line-range overlap detection
- [ ] Implement `has_line_overlap` property
- [ ] Write tests with known overlapping and non-overlapping PRs

## Deliverables
- [ ] Diff parser that handles all standard git diff formats
- [ ] File overlap detection between any pair of PRs
- [ ] 90%+ test coverage on diff_parser.py

## Acceptance Criteria
- [ ] parse_unified_diff correctly handles: modifications, additions, deletions, renames
- [ ] FileOverlap.has_line_overlap correctly detects overlapping line ranges
- [ ] All tests pass with fixture diffs
