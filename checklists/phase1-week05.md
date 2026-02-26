# Phase 1 — Week 5: GitHub Action + PR Comment Output

## Goals
- Package as a GitHub Action and post formatted comments

## Daily Tasks

### Day 1-2: Comment Formatter
- [ ] Implement `format_report()` in github_comment.py
- [ ] Color-coded severity (emoji + bold type labels)
- [ ] Collapsible section for info-level conflicts
- [ ] Clickable PR links
- [ ] Clean PR list (no conflicts)
- [ ] Footer with analysis duration

### Day 3-4: GitHub Action Packaging
- [ ] Create action.yml with inputs and outputs
- [ ] Create Dockerfile (python:3.12-slim + uv)
- [ ] Create entrypoint.sh script
- [ ] Test action locally with `act` or manual Docker build

### Day 5: End-to-End Testing
- [ ] Test full pipeline: PR event → analysis → comment posted
- [ ] Verify comment is posted/updated correctly
- [ ] Verify commit status is set correctly
- [ ] Test with real GitHub repository

## Deliverables
- [ ] GitHub Action ready for marketplace
- [ ] Beautiful PR comment formatting
- [ ] Docker image builds successfully

## Acceptance Criteria
- [ ] Action runs on PR events and posts formatted comments
- [ ] Comments include risk score, conflict details, and recommendations
- [ ] Existing MergeGuard comments are updated (not duplicated)
