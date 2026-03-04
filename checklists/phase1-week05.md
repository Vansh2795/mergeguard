# Phase 1 — Week 5: GitHub Action + PR Comment Output

## Goals
- Package as a GitHub Action and post formatted comments

## Daily Tasks

### Day 1-2: Comment Formatter
- [x] Implement `format_report()` in github_comment.py
- [x] Color-coded severity (emoji + bold type labels)
- [x] Collapsible section for info-level conflicts
- [x] Clickable PR links
- [x] Clean PR list (no conflicts)
- [x] Footer with analysis duration

### Day 3-4: GitHub Action Packaging
- [x] Create action.yml with inputs and outputs
- [x] Create Dockerfile (python:3.12-slim + uv)
- [x] Create entrypoint.sh script
- [x] Test action locally with `act` or manual Docker build

### Day 5: End-to-End Testing
- [x] Test full pipeline: PR event → analysis → comment posted
- [x] Verify comment is posted/updated correctly
- [x] Verify commit status is set correctly
- [x] Test with real GitHub repository

## Deliverables
- [x] GitHub Action ready for marketplace
- [x] Beautiful PR comment formatting
- [x] Docker image builds successfully

## Acceptance Criteria
- [x] Action runs on PR events and posts formatted comments
- [x] Comments include risk score, conflict details, and recommendations
- [x] Existing MergeGuard comments are updated (not duplicated)
