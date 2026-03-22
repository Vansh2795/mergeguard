# v0.5 — Feature 13: Multi-Repo Service Mesh (Cross-Service Conflict Detection)

## Goals
- Detect cross-service conflicts: PR A changes an API contract in service X, PR B in service Y calls that API
- Promote `analyze-multi` from a separate command into a first-class integrated feature
- Provide org-level dashboard showing conflicts across all repositories

## Daily Tasks

### Day 1-2: Service Manifest & Discovery
- [ ] Define `mergeguard-services.yml` manifest format: list of repos with their API boundaries, communication protocols, and shared schema paths
- [ ] Create `analysis/service_mesh.py` module
- [ ] Implement manifest parser: `load_service_manifest(path: str) -> ServiceMesh`
- [ ] Create `ServiceMesh` model in `models.py`: `services: list[Service]`, `Service` has `repo`, `api_paths` (globs), `consumers` (list of repo names), `protocol` (REST/gRPC/GraphQL)
- [ ] Implement auto-discovery: detect API boundaries from common patterns (OpenAPI specs, proto files, GraphQL schemas)
- [ ] Support GitHub org-level API: list all repos, detect which have MergeGuard installed

### Day 3: Cross-Repo Conflict Detection
- [ ] Extend `core/engine.py` to accept a `ServiceMesh` context for multi-repo analysis
- [ ] For each PR that modifies API boundary files: fetch open PRs from consumer services
- [ ] Detect interface conflicts: API signature changed in provider, caller in consumer uses old signature
- [ ] Detect schema conflicts: shared proto/OpenAPI schema modified in one repo, consumers not updated
- [ ] Add `CROSS_SERVICE` value to `ConflictType` enum in `models.py`
- [ ] Add `source_repo` and `target_repo` fields to `Conflict` model for cross-repo conflicts

### Day 4: Multi-Repo Dashboard & Notifications
- [ ] Extend `output/dashboard_html.py` with org-level view: services as nodes, conflicts as edges
- [ ] Show cross-service conflict details: which API endpoint, which consumer, which PRs
- [ ] Extend `output/notifications.py` to notify both provider and consumer teams
- [ ] Cross-repo PR comments: "This PR changes an API used by [checkout-service PR #45]"
- [ ] Add `--service-mesh` flag to `mergeguard analyze` and `mergeguard analyze-multi` CLI commands
- [ ] Merge `analyze-multi` functionality into default `analyze` when service mesh config is present

### Day 5: GitHub App & Testing
- [ ] Support org-level GitHub App installation for multi-repo access (extend `integrations/github_app.py` from Feature 04)
- [ ] Implement cross-repo token management: single installation token covers all org repos
- [ ] Test with mock microservice setup: 3 repos with REST API contracts
- [ ] Test API boundary detection with OpenAPI spec changes
- [ ] Test cross-repo notification routing: provider team and consumer team both notified
- [ ] Verify performance: cross-repo analysis for 5 services with 50 total open PRs completes in under 60 seconds

## Deliverables
- [ ] `analysis/service_mesh.py` — service manifest parser and cross-repo analysis
- [ ] `mergeguard-services.yml` manifest format with auto-discovery
- [ ] `CROSS_SERVICE` conflict type with cross-repo fields
- [ ] Org-level dashboard with service mesh visualization
- [ ] Integrated multi-repo analysis in default `analyze` command

## Acceptance Criteria
- [ ] Cross-service API conflicts detected: provider changes API, consumer PR flagged
- [ ] Service mesh manifest defines repo relationships and API boundaries
- [ ] Auto-discovery detects API boundaries from OpenAPI/proto/GraphQL files
- [ ] Org-level dashboard shows service graph with conflict edges highlighted
- [ ] Both provider and consumer teams notified of cross-service conflicts
- [ ] `analyze` command automatically includes cross-repo analysis when service mesh config exists
- [ ] Single GitHub App installation covers all repos in the org

> **Extend:** `models.py` (ServiceMesh model, CROSS_SERVICE conflict type, cross-repo fields on Conflict), `core/engine.py` (multi-repo analysis with service context), `output/dashboard_html.py` (org-level view), `output/notifications.py` (cross-repo routing), `output/github_comment.py` (cross-repo links), `cli.py` (--service-mesh flag, integrate analyze-multi). **New:** `analysis/service_mesh.py`, `mergeguard-services.yml` format.
