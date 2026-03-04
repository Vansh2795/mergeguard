# Phase 1 — Week 4: Conflict Classification Engine

## Goals
- Classify conflicts into hard, interface, behavioral, and duplication types

## Daily Tasks

### Day 1-3: Core Classification Algorithm
- [x] Implement hard conflict detection (same symbol, overlapping lines)
- [x] Implement interface conflict detection (signature change + callers)
- [x] Implement behavioral conflict detection (same function, different lines)
- [x] Implement duplication detection (similar new symbols)
- [x] Create `classify_conflicts()` function
- [x] Assign severity levels based on conflict type and context

### Day 4-5: Integration Test
- [x] Create fixture repository with 3 branches and known conflicts
- [x] Run full pipeline: fetch → parse → detect → classify
- [x] Verify all expected conflicts found with correct types/severities
- [x] Test edge cases: no conflicts, all-critical conflicts, mixed

## Deliverables
- [x] Complete conflict classification engine
- [x] Full pipeline integration test with fixture data

## Acceptance Criteria
- [x] Hard conflicts detected when same lines modified
- [x] Interface conflicts detected when signature changes affect callers
- [x] Behavioral conflicts detected when same function modified differently
- [x] No false positives for non-overlapping PRs
