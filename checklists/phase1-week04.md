# Phase 1 — Week 4: Conflict Classification Engine

## Goals
- Classify conflicts into hard, interface, behavioral, and duplication types

## Daily Tasks

### Day 1-3: Core Classification Algorithm
- [ ] Implement hard conflict detection (same symbol, overlapping lines)
- [ ] Implement interface conflict detection (signature change + callers)
- [ ] Implement behavioral conflict detection (same function, different lines)
- [ ] Implement duplication detection (similar new symbols)
- [ ] Create `classify_conflicts()` function
- [ ] Assign severity levels based on conflict type and context

### Day 4-5: Integration Test
- [ ] Create fixture repository with 3 branches and known conflicts
- [ ] Run full pipeline: fetch → parse → detect → classify
- [ ] Verify all expected conflicts found with correct types/severities
- [ ] Test edge cases: no conflicts, all-critical conflicts, mixed

## Deliverables
- [ ] Complete conflict classification engine
- [ ] Full pipeline integration test with fixture data

## Acceptance Criteria
- [ ] Hard conflicts detected when same lines modified
- [ ] Interface conflicts detected when signature changes affect callers
- [ ] Behavioral conflicts detected when same function modified differently
- [ ] No false positives for non-overlapping PRs
