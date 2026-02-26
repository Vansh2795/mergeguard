# Phase 3 — Week 19: GitLab Support

## Goals
- Abstract VCS client interface and implement GitLab support

## Daily Tasks

### Day 1-2: VCS Abstraction
- [ ] Define abstract VCS client interface (Protocol class)
- [ ] Refactor GitHubClient to implement the interface
- [ ] Update engine to accept any VCS client
- [ ] Verify existing tests still pass

### Day 3-4: GitLab Client
- [ ] Implement GitLabClient with python-gitlab or httpx
- [ ] Map GitLab MR API to shared interface
- [ ] Handle GitLab-specific features (MR approvals, etc.)
- [ ] Test with GitLab.com API

### Day 5: Testing
- [ ] Integration tests with mocked GitLab API
- [ ] Verify feature parity with GitHub client
- [ ] Update CLI to support --provider flag
- [ ] Update documentation

## Deliverables
- [ ] Abstract VCS client interface
- [ ] Working GitLab client
- [ ] CLI support for both platforms

## Acceptance Criteria
- [ ] GitLab MRs analyzed with same accuracy as GitHub PRs
- [ ] Existing GitHub tests unaffected by refactoring
- [ ] CLI auto-detects platform from remote URL
