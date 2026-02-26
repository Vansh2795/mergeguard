# Phase 3 — Week 13: Guardrails Engine (Part 1)

## Goals
- Parse and enforce basic guardrail rules from .mergeguard.yml

## Daily Tasks

### Day 1-2: Rule Parsing
- [ ] Parse `rules` section from .mergeguard.yml
- [ ] Validate rule syntax with Pydantic
- [ ] Support `pattern`, `when`, `message` fields
- [ ] Support `max_files_changed`, `max_lines_changed`

### Day 3-4: Basic Enforcement
- [ ] Implement file pattern matching (fnmatch)
- [ ] Enforce size limits (files changed, lines changed)
- [ ] Enforce AI-specific rules (`when: ai_authored`)
- [ ] Generate Conflict objects for violations

### Day 5: Testing
- [ ] Test rule parsing with various configs
- [ ] Test size limit enforcement
- [ ] Test AI-specific rule activation
- [ ] Test rule violation reporting

## Deliverables
- [ ] Guardrail rule parser
- [ ] Basic rule enforcement (size limits, AI rules)
- [ ] Violations shown in PR comments

## Acceptance Criteria
- [ ] Rules parsed correctly from YAML config
- [ ] Size limit violations detected
- [ ] AI rules only trigger for AI-authored PRs
