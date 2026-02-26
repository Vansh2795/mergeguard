# Phase 3 — Week 14: Guardrails (Part 2) — Dependencies & Patterns

## Goals
- Enforce import dependency rules and code pattern rules

## Daily Tasks

### Day 1-2: Import Dependency Rules
- [ ] Implement `cannot_import_from` enforcement
- [ ] Use import graph to detect forbidden imports
- [ ] Support glob patterns for module paths
- [ ] Generate clear violation messages

### Day 3-4: Pattern Rules
- [ ] Implement `must_not_contain` pattern checking
- [ ] Implement `max_cyclomatic_complexity` (basic)
- [ ] Implement `max_function_lines`
- [ ] Use AST data for accurate function length measurement

### Day 5: Integration + Testing
- [ ] Wire guardrails into the main engine
- [ ] Test with realistic monorepo configs
- [ ] Test all rule types
- [ ] Performance test (rules don't significantly slow analysis)

## Deliverables
- [ ] Import dependency enforcement
- [ ] Code pattern enforcement
- [ ] Complete guardrails engine

## Acceptance Criteria
- [ ] Forbidden imports detected accurately
- [ ] Pattern violations reported with clear messages
- [ ] Guardrails add < 5% to analysis time
