# v0.5 — Feature 10: Self-Hosted Deployment (Docker Compose / Helm)

## Goals
- Provide production-ready deployment configs for enterprise infrastructure
- Support Docker Compose for simple setups and Helm for Kubernetes deployments
- Follow 12-factor app principles with environment variable configuration

## Daily Tasks

### Day 1-2: Docker Production Image
- [ ] Create optimized `Dockerfile` (multi-stage build: build stage with uv + deps, runtime stage with python:3.12-slim)
- [ ] Include webhook server, CLI, and all optional dependencies (LLM, MCP) in the image
- [ ] Configure non-root user, health check, and proper signal handling (SIGTERM graceful shutdown)
- [ ] Create `.dockerignore` excluding tests, docs, checklists, .git
- [ ] Add environment variable documentation: all config options mappable to env vars (`MERGEGUARD_*` prefix)
- [ ] Implement env-to-config bridge in `config.py`: `MERGEGUARD_RISK_THRESHOLD`, `MERGEGUARD_LLM_ENABLED`, etc.

### Day 3: Docker Compose Stack
- [ ] Create `docker-compose.yml` with services: `mergeguard-server` (webhook + API), `redis` (optional queue backend)
- [ ] Add volume mount for SQLite databases: `.mergeguard-cache/` persisted across restarts
- [ ] Add volume mount for config: `.mergeguard.yml` bind mount
- [ ] Configure networking: expose port 8080 for webhooks, internal network for Redis
- [ ] Add `docker-compose.override.yml` for development (hot reload, debug logging, exposed ports)
- [ ] Create `scripts/docker-entrypoint.sh` with config validation on startup

### Day 4: Kubernetes / Helm Chart
- [ ] Create `helm/mergeguard/` chart directory structure
- [ ] Implement `Deployment` for webhook server with configurable replicas, resources, probes
- [ ] Implement `Service` (ClusterIP) and optional `Ingress` with TLS termination
- [ ] Implement `ConfigMap` for `.mergeguard.yml` and `Secret` for tokens
- [ ] Implement `PersistentVolumeClaim` for SQLite data (or optional PostgreSQL subchart)
- [ ] Add `values.yaml` with sensible defaults and full documentation comments
- [ ] Add `HorizontalPodAutoscaler` based on webhook queue depth

### Day 5: Security, Monitoring & Documentation
- [ ] Add rate limiting to webhook endpoint (configurable requests/minute per repo)
- [ ] Add authentication for API endpoints (API key or bearer token)
- [ ] Add health check endpoints: `/health` (liveness), `/ready` (readiness — checks DB and SCM connectivity)
- [ ] Document deployment guide: GitHub Enterprise Server + self-hosted MergeGuard setup
- [ ] Document Helm installation: `helm install mergeguard ./helm/mergeguard -f values.yaml`
- [ ] Test full deployment: webhook → analysis → PR comment cycle in Docker Compose

## Deliverables
- [ ] Optimized multi-stage `Dockerfile`
- [ ] `docker-compose.yml` and `docker-compose.override.yml`
- [ ] Helm chart (`helm/mergeguard/`) with Deployment, Service, Ingress, ConfigMap, Secret, PVC, HPA
- [ ] Environment variable configuration bridge
- [ ] Deployment documentation for Docker Compose and Kubernetes

## Acceptance Criteria
- [ ] `docker compose up` starts a working MergeGuard server that receives webhooks and posts PR comments
- [ ] All configuration possible via environment variables (no file editing required for basic setup)
- [ ] Helm chart installs on Kubernetes with `helm install` and passes `helm lint`
- [ ] Health/readiness probes work correctly for container orchestration
- [ ] SQLite data persists across container restarts via volume mount
- [ ] Rate limiting and authentication protect webhook endpoints from abuse
- [ ] Image size under 200MB

> **Extend:** `config.py` (env var bridge), `server/webhook.py` (auth, rate limiting, health checks). **New:** `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `helm/mergeguard/` chart, `scripts/docker-entrypoint.sh`.
