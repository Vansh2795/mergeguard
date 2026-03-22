# v0.5 — Feature 09: Secret & Security Scanning Integration

## Goals
- Detect accidentally committed secrets in PR diffs during conflict analysis
- Surface findings as a new SECURITY conflict type with CRITICAL severity
- Integrate with existing SARIF output and GitHub Advanced Security API

## Daily Tasks

### Day 1-2: Secret Detection Engine
- [ ] Create `analysis/secret_scanner.py` module
- [ ] Implement regex patterns for common secrets: AWS access keys, GitHub tokens (ghp_/gho_/ghs_), private keys (RSA/EC), database connection strings, Slack tokens, Stripe keys, generic high-entropy strings
- [ ] Scan only added lines in PR diffs (not removed lines or context) using `analysis/diff_parser.py` `DiffHunk.added_lines`
- [ ] Implement entropy-based detection for generic secrets (Shannon entropy > threshold on hex/base64 strings)
- [ ] Support allowlisting: `security.allow_patterns` in config for known false positives (test fixtures, example keys)
- [ ] Return `SecretFinding` objects: `file_path`, `line_number`, `secret_type`, `masked_value`, `confidence`

### Day 3: Integration with Conflict Pipeline
- [ ] Add `SECURITY` value to `ConflictType` enum in `models.py`
- [ ] Generate `Conflict` objects from `SecretFinding` results with severity always CRITICAL
- [ ] Wire secret scanning into `core/engine.py` — run after diff parsing, before conflict classification
- [ ] Add `security` section to `.mergeguard.yml`: `secret_scanning` (bool), `patterns` (list of custom regex), `allow_patterns` (list), `entropy_threshold` (float, default: 4.5)
- [ ] Ensure secret findings appear in all output formats (terminal, comment, JSON, HTML)

### Day 4: SARIF & GitHub Advanced Security
- [ ] Extend `output/sarif.py` with SECURITY rule ID: `mergeguard/secret-detected`
- [ ] Map `SecretFinding.secret_type` to SARIF rule descriptions
- [ ] Add SARIF severity mapping: all secrets → `error` level
- [ ] Integrate with GitHub Advanced Security API: `GET /repos/{owner}/{repo}/code-scanning/alerts` to pull existing alerts and deduplicate
- [ ] Support uploading SARIF results via `POST /repos/{owner}/{repo}/code-scanning/sarifs` for GitHub Code Scanning integration

### Day 5: Testing & Edge Cases
- [ ] Test detection of all supported secret types against known test patterns
- [ ] Test false positive rate: scan common codebases, verify allowlist suppresses test fixtures
- [ ] Test entropy detection: verify it catches generic API keys without too many false positives
- [ ] Test SARIF output validates against SARIF schema
- [ ] Test integration with inline annotations (Feature 01): secrets flagged on the exact line
- [ ] Verify masked values never expose actual secrets in logs, comments, or reports

## Deliverables
- [ ] `analysis/secret_scanner.py` — regex + entropy-based secret detection
- [ ] `SECURITY` conflict type integrated into the analysis pipeline
- [ ] Extended SARIF output with security findings
- [ ] GitHub Advanced Security API integration (pull alerts, upload SARIF)
- [ ] Security config section in `.mergeguard.yml`

## Acceptance Criteria
- [ ] Detects AWS keys, GitHub tokens, private keys, and connection strings in PR diffs
- [ ] All secret findings surfaced as CRITICAL severity conflicts
- [ ] Masked values in all outputs — actual secret content never exposed
- [ ] SARIF output includes security findings and validates against schema
- [ ] Allowlist suppresses known false positives (test data, examples)
- [ ] Scanning adds less than 1 second to analysis time for typical PR diffs

> **Extend:** `models.py` (SECURITY conflict type, SecretFinding model), `core/engine.py` (scanning step), `output/sarif.py` (security rules), `output/github_comment.py` (secret warnings), `config.py` (security section). **New:** `analysis/secret_scanner.py`.
