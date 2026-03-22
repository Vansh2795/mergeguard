# v0.5 — Feature 11: AI Conflict Resolution Agent

## Goals
- Close the detect-to-fix loop: detect conflict → generate resolution → propose fix as PR suggestion
- Use LLM-powered analysis to generate merge conflict resolutions with confidence scoring
- Ensure all generated patches are reviewed by humans before merge

## Daily Tasks

### Day 1-2: Resolution Strategy Framework
- [ ] Create `core/resolution.py` module
- [ ] Define resolution strategies: `KEEP_SOURCE` (keep PR A's changes), `KEEP_TARGET` (keep PR B's changes), `MERGE_BOTH` (combine both), `REWRITE` (LLM-generated new code)
- [ ] Implement deterministic resolvers for simple cases: identical additions → deduplicate, non-overlapping hunks → merge both
- [ ] Create `Resolution` model in `models.py`: `conflict`, `strategy`, `patch` (unified diff), `confidence` (0.0-1.0), `explanation`
- [ ] Add `resolve_conflicts(conflicts: list[Conflict]) -> list[Resolution]` orchestrator

### Day 3: LLM-Powered Resolution
- [ ] Extend `integrations/llm_analyzer.py` with `generate_resolution(conflict: Conflict) -> Resolution` method
- [ ] Design prompt: provide both PR diffs, conflict context, symbol signatures, and ask for merged resolution
- [ ] Parse LLM response into a valid unified diff patch
- [ ] Implement confidence scoring: high (>0.8) for simple merges, medium (0.5-0.8) for logic changes, low (<0.5) for complex refactors
- [ ] Add token budget management: skip resolution for conflicts with >5000 token diff context
- [ ] Support both Anthropic and OpenAI backends (extend existing `llm_provider` config)

### Day 4: PR Integration
- [ ] Post resolutions as GitHub PR review suggestions using suggestion blocks (```suggestion)
- [ ] Group all suggestions into a single review with explanatory body
- [ ] For low-confidence resolutions: post as comment with "Suggested resolution (low confidence)" prefix
- [ ] For high-confidence resolutions: post as actionable suggestion that can be committed from GitHub UI
- [ ] Add `--resolve` flag to `mergeguard analyze` CLI command
- [ ] Add `resolution` section to `.mergeguard.yml`: `enabled`, `auto_suggest` (bool), `min_confidence` (float), `max_conflicts` (int)

### Day 5: Safety & Testing
- [ ] Validate generated patches: ensure they apply cleanly to the target branch
- [ ] Reject resolutions that introduce syntax errors (run through tree-sitter parse validation from `analysis/ast_parser.py`)
- [ ] Test with known conflict patterns: same-line edit, function signature change, import addition
- [ ] Test confidence scoring calibration: high confidence should have >90% acceptance rate
- [ ] Test token budget limits: large diffs gracefully skip resolution
- [ ] Verify no resolution is auto-applied — all require human review/approval

## Deliverables
- [ ] `core/resolution.py` — resolution strategy framework and orchestrator
- [ ] Extended `LLMAnalyzer` with resolution generation
- [ ] GitHub suggestion block integration
- [ ] Confidence scoring for all resolutions
- [ ] Resolution config section in `.mergeguard.yml`

## Acceptance Criteria
- [ ] Simple conflicts (non-overlapping hunks, identical additions) resolved deterministically without LLM
- [ ] Complex conflicts get LLM-generated resolutions with confidence scores
- [ ] All resolutions posted as reviewable suggestions — never auto-applied
- [ ] Generated patches validate: apply cleanly and pass syntax check
- [ ] Low-confidence resolutions clearly labeled as such in PR comments
- [ ] Resolution disabled by default, opt-in via config

> **Extend:** `models.py` (Resolution model), `integrations/llm_analyzer.py` (resolution generation), `output/github_comment.py` (suggestion blocks), `core/engine.py` (resolution step), `cli.py` (--resolve flag), `config.py` (resolution section). **New:** `core/resolution.py`.
