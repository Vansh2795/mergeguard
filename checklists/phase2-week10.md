# Phase 2 — Week 10: Regression Detection

## Goals
- Detect when PRs re-introduce recently removed or migrated code

## Daily Tasks

### Day 1-3: Regression Detection Algorithm
- [x] Implement `find_regressions()` in decisions_log.py
- [x] Match PR symbols against REMOVAL decisions
- [x] Match PR files against MIGRATION decisions
- [x] Convert regression matches to Conflict objects
- [x] Implement regression severity classification

### Day 4-5: Integration + Testing
- [x] Wire regression detection into the engine
- [x] Create test fixtures with deliberate regressions
- [x] Test: PR re-adds a removed function → detected
- [x] Test: PR uses old pattern after migration → detected
- [x] Test: no false positives for unrelated changes

## Deliverables
- [x] Regression detection against decisions log
- [x] Regression conflicts shown in PR comments
- [x] Integration with risk scoring

## Acceptance Criteria
- [x] Regressions detected with correct severity
- [x] Regression description includes original PR reference
- [x] No false positives for normal code additions

> **Note:** `detect_regressions()` is fully implemented in `core/regression.py` and wired into the engine (Gap #13 fixed). Regression conflicts are appended to `all_conflicts` and flow through risk scoring and PR comments.
