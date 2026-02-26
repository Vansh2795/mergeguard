# Phase 2 — Week 8: Risk Scoring System (Part 2)

## Goals
- Complete composite risk scoring with all 5 factors

## Daily Tasks

### Day 1-2: Pattern Deviation Score
- [ ] Implement AST comparison for coding pattern consistency
- [ ] Compare symbol signatures against module averages
- [ ] Detect unusual patterns (very long functions, deep nesting)
- [ ] Normalize to 0-1 scale

### Day 3-4: Churn Risk + Composite Score
- [ ] Implement churn risk from git history (revert/hotfix rate)
- [ ] Combine all 5 factors with configured weights
- [ ] Implement `compute_risk_score()` returning (score, breakdown)
- [ ] Ensure score is clamped to 0-100

### Day 5: Testing + Tuning
- [ ] Test with realistic scenarios (high/medium/low risk)
- [ ] Verify weight contributions match expectations
- [ ] Tune default weights based on test results
- [ ] Write comprehensive tests for edge cases

## Deliverables
- [ ] Complete risk scoring with all 5 factors
- [ ] Transparent breakdown dict for each factor
- [ ] Tuned default weights

## Acceptance Criteria
- [ ] Zero-risk PR (no conflicts, no dependencies) scores 0
- [ ] High-risk PR (critical conflict, deep deps, AI) scores > 70
- [ ] Risk breakdown shows individual factor contributions
