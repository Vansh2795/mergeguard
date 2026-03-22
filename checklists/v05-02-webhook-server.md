# v0.5 — Feature 02: Webhook-Driven Real-Time Analysis

## Goals
- Provide instant conflict detection when PRs are opened, updated, or closed
- Eliminate dependency on scheduled CI runs for conflict analysis
- Support GitHub, GitLab, and Bitbucket webhook event formats

## Daily Tasks

### Day 1-2: Webhook Server Core
- [x] Create `server/` package under `src/mergeguard/`
- [x] Implement FastAPI app in `server/webhook.py` with webhook endpoints
- [x] Add `/webhooks/github`, `/webhooks/gitlab`, `/webhooks/bitbucket` routes
- [x] Verify webhook signatures (HMAC-SHA256 for GitHub, token for GitLab, JWT for Bitbucket)
- [x] Parse webhook payloads into normalized event objects
- [x] Handle events: `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.reopened`

### Day 3: Targeted Analysis Pipeline
- [x] On PR open/update: analyze only the affected PR against existing open PRs (not full O(n^2) scan)
- [x] On PR close/merge: update conflict graph, re-notify PRs that previously conflicted with the closed PR
- [x] Use `storage/cache.py` `AnalysisCache` for incremental analysis — skip unchanged PRs
- [x] Implement background task queue using asyncio (in-process) with optional Redis/Celery adapter
- [x] Rate limit analysis per repo to avoid thundering herd on mass PR updates

### Day 4: CLI & Configuration
- [x] Add `mergeguard serve` command to `cli.py` with `--port`, `--host`, `--workers` options
- [x] Add health check endpoint: `GET /health` returning server status and last analysis time
- [x] Add webhook secret configuration via env vars: `MERGEGUARD_WEBHOOK_SECRET_GITHUB`, etc.
- [x] Add `server` section to `.mergeguard.yml`: `port`, `workers`, `analysis_timeout`, `queue_backend`
- [x] Implement graceful shutdown with in-flight analysis completion

### Day 5: Docker & Deployment
- [x] Create `Dockerfile` for the webhook server (python:3.12-slim + uv + fastapi)
- [x] Create `docker-compose.yml` with server + optional Redis
- [x] Add Prometheus metrics endpoint: `/metrics` with analysis_duration, queue_depth, webhook_count
- [x] Test with GitHub webhook delivery (use smee.io for local testing)
- [x] Test with GitLab and Bitbucket webhook delivery
- [x] Document webhook setup instructions per platform

## Deliverables
- [x] `server/webhook.py` — FastAPI webhook receiver with signature verification
- [x] `server/queue.py` — Background analysis task queue (asyncio + optional Redis)
- [x] `mergeguard serve` CLI command
- [x] Dockerfile and docker-compose.yml
- [x] Health check and metrics endpoints

## Acceptance Criteria
- [x] PR open/update triggers conflict analysis within 10 seconds for repos with <50 open PRs
- [x] Webhook signatures verified for all three platforms (rejects invalid signatures with 401)
- [x] PR close/merge updates conflict state and notifies previously-conflicting PRs
- [x] Server handles concurrent webhooks without race conditions
- [x] Docker image builds and runs with `docker compose up`
- [x] Health check returns 200 with status info

> **Extend:** `cli.py` (new `serve` command), `core/engine.py` (targeted single-PR analysis mode), `storage/cache.py` (invalidation on PR events), `models.py` (server config section). **New:** `server/webhook.py`, `server/queue.py`, `Dockerfile`, `docker-compose.yml`.
