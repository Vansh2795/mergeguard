# Phase 2 — Week 8: Risk Scoring System (Part 2)

## Goals
- Complete composite risk scoring with all 5 factors

## Daily Tasks

### Day 1-2: Pattern Deviation Score
- [x] Implement AST comparison for coding pattern consistency
- [x] Compare symbol signatures against module averages
- [x] Detect unusual patterns (very long functions, deep nesting)
- [x] Normalize to 0-1 scale

### Day 3-4: Churn Risk + Composite Score
- [x] Implement churn risk from git history (revert/hotfix rate)
- [x] Combine all 5 factors with configured weights
- [x] Implement `compute_risk_score()` returning (score, breakdown)
- [x] Ensure score is clamped to 0-100

### Day 5: Testing + Tuning
- [x] Test with realistic scenarios (high/medium/low risk)
- [x] Verify weight contributions match expectations
- [x] Tune default weights based on test results
- [x] Write comprehensive tests for edge cases

## Deliverables
- [x] Complete risk scoring with all 5 factors
- [x] Transparent breakdown dict for each factor
- [x] Tuned default weights

## Acceptance Criteria
- [x] Zero-risk PR (no conflicts, no dependencies) scores 0
- [x] High-risk PR (critical conflict, deep deps, AI) scores > 70
- [x] Risk breakdown shows individual factor contributions
