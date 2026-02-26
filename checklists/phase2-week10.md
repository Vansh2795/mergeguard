# Phase 2 — Week 10: Regression Detection

## Goals
- Detect when PRs re-introduce recently removed or migrated code

## Daily Tasks

### Day 1-3: Regression Detection Algorithm
- [ ] Implement `find_regressions()` in decisions_log.py
- [ ] Match PR symbols against REMOVAL decisions
- [ ] Match PR files against MIGRATION decisions
- [ ] Convert regression matches to Conflict objects
- [ ] Implement regression severity classification

### Day 4-5: Integration + Testing
- [ ] Wire regression detection into the engine
- [ ] Create test fixtures with deliberate regressions
- [ ] Test: PR re-adds a removed function → detected
- [ ] Test: PR uses old pattern after migration → detected
- [ ] Test: no false positives for unrelated changes

## Deliverables
- [ ] Regression detection against decisions log
- [ ] Regression conflicts shown in PR comments
- [ ] Integration with risk scoring

## Acceptance Criteria
- [ ] Regressions detected with correct severity
- [ ] Regression description includes original PR reference
- [ ] No false positives for normal code additions
