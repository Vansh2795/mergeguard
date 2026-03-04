# Phase 3 — Week 13: Guardrails Engine (Part 1)

## Goals
- Parse and enforce basic guardrail rules from .mergeguard.yml

## Daily Tasks

### Day 1-2: Rule Parsing
- [x] Parse `rules` section from .mergeguard.yml
- [x] Validate rule syntax with Pydantic
- [x] Support `pattern`, `when`, `message` fields
- [x] Support `max_files_changed`, `max_lines_changed`

### Day 3-4: Basic Enforcement
- [x] Implement file pattern matching (fnmatch)
- [x] Enforce size limits (files changed, lines changed)
- [x] Enforce AI-specific rules (`when: ai_authored`)
- [x] Generate Conflict objects for violations

### Day 5: Testing
- [x] Test rule parsing with various configs
- [x] Test size limit enforcement
- [x] Test AI-specific rule activation
- [x] Test rule violation reporting

## Deliverables
- [x] Guardrail rule parser
- [x] Basic rule enforcement (size limits, AI rules)
- [x] Violations shown in PR comments

## Acceptance Criteria
- [x] Rules parsed correctly from YAML config
- [x] Size limit violations detected
- [x] AI rules only trigger for AI-authored PRs

> **Note:** `guardrails.py` is fully implemented with `enforce_guardrails()` and wired into the engine pipeline. Guardrail violations are added to `all_conflicts` and appear in PR comments.
