"""Integration tests for the webhook server — full end-to-end with httpx TestClient."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed (server extras)")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from mergeguard.server.webhook import app, lifespan  # noqa: E402

# ── Test secrets & signing helpers ──────────────────────────────────

_GH_SECRET = "test-gh-secret"
_GL_SECRET = "test-gl-secret"
_BB_SECRET = "test-bb-secret"


def _sign_github(payload: bytes, secret: str) -> str:
    """Compute GitHub HMAC-SHA256 signature."""
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _sign_bitbucket(payload: bytes, secret: str) -> str:
    """Compute Bitbucket HMAC-SHA256 signature."""
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def _webhook_secrets(monkeypatch):
    """Set webhook secrets for all platforms."""
    monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITHUB", _GH_SECRET)
    monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITLAB", _GL_SECRET)
    monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_BITBUCKET", _BB_SECRET)


@pytest.fixture
async def client(_webhook_secrets):
    """Async httpx client with lifespan initialized."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert "queue_pending" in data


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_returns_prometheus_format(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "mergeguard_uptime_seconds" in resp.text
        assert "mergeguard_webhooks_received_total" in resp.text


class TestGitHubWebhook:
    def _github_payload(self, action: str = "opened") -> dict:
        return {
            "action": action,
            "pull_request": {
                "number": 42,
                "head": {"sha": "abc123"},
                "base": {"ref": "main"},
            },
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "alice"},
        }

    @pytest.mark.asyncio
    async def test_pr_opened_queues_analysis(self, client):
        payload = json.dumps(self._github_payload("opened")).encode()
        sig = _sign_github(payload, _GH_SECRET)
        resp = await client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "x-github-event": "pull_request",
                "x-hub-signature-256": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
        assert resp.json()["pr"] == 42

    @pytest.mark.asyncio
    async def test_push_event_ignored(self, client):
        payload = json.dumps({"ref": "refs/heads/main"}).encode()
        sig = _sign_github(payload, _GH_SECRET)
        resp = await client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "x-github-event": "push",
                "x-hub-signature-256": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, client):
        payload = json.dumps(self._github_payload()).encode()
        resp = await client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "x-github-event": "pull_request",
                "x-hub-signature-256": "sha256=invalid",
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self, client):
        payload = json.dumps(self._github_payload()).encode()
        sig = _sign_github(payload, _GH_SECRET)
        resp = await client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "x-github-event": "pull_request",
                "x-hub-signature-256": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200


class TestGitHubMergeGroupWebhook:
    def _merge_group_payload(self) -> dict:
        return {
            "action": "checks_requested",
            "merge_group": {
                "head_sha": "merge_sha_123",
                "base_ref": "refs/heads/main",
                "head_ref": "refs/heads/gh-readonly-queue/main/pr-42-abc",
                "head_commit": {
                    "message": "Merge pull request #42",
                },
            },
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "github-merge-queue[bot]"},
        }

    @pytest.mark.asyncio
    async def test_merge_group_queued(self, client):
        payload = json.dumps(self._merge_group_payload()).encode()
        sig = _sign_github(payload, _GH_SECRET)
        resp = await client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "x-github-event": "merge_group",
                "x-hub-signature-256": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["type"] == "merge_group"
        assert 42 in data["prs"]


class TestGitLabWebhook:
    def _gitlab_payload(self) -> dict:
        return {
            "object_attributes": {
                "action": "open",
                "iid": 10,
                "last_commit": {"id": "def456"},
                "target_branch": "main",
            },
            "project": {"path_with_namespace": "group/project"},
            "user": {"username": "bob"},
        }

    @pytest.mark.asyncio
    async def test_mr_opened_queues_analysis(self, client):
        resp = await client.post(
            "/webhooks/gitlab",
            json=self._gitlab_payload(),
            headers={
                "x-gitlab-event": "Merge Request Hook",
                "x-gitlab-token": _GL_SECRET,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, client):
        resp = await client.post(
            "/webhooks/gitlab",
            json=self._gitlab_payload(),
            headers={
                "x-gitlab-event": "Merge Request Hook",
                "x-gitlab-token": "wrong-token",
            },
        )
        assert resp.status_code == 401


class TestBitbucketWebhook:
    def _bb_payload(self) -> dict:
        return {
            "pullrequest": {
                "id": 7,
                "source": {"commit": {"hash": "ghi789"}},
                "destination": {"branch": {"name": "main"}},
            },
            "repository": {"full_name": "workspace/repo"},
            "actor": {"username": "carol"},
        }

    @pytest.mark.asyncio
    async def test_pr_created_queues_analysis(self, client):
        payload = json.dumps(self._bb_payload()).encode()
        sig = _sign_bitbucket(payload, _BB_SECRET)
        resp = await client.post(
            "/webhooks/bitbucket",
            content=payload,
            headers={
                "x-event-key": "pullrequest:created",
                "x-hub-signature": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_push_event_ignored(self, client):
        payload = json.dumps({"push": {}}).encode()
        sig = _sign_bitbucket(payload, _BB_SECRET)
        resp = await client.post(
            "/webhooks/bitbucket",
            content=payload,
            headers={
                "x-event-key": "repo:push",
                "x-hub-signature": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


class TestMissingSecretReturns403:
    """Endpoints must reject with 403 when webhook secret is not configured."""

    @pytest.mark.asyncio
    async def test_github_no_secret_returns_403(self, monkeypatch):
        monkeypatch.delenv("MERGEGUARD_WEBHOOK_SECRET_GITHUB", raising=False)
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITLAB", _GL_SECRET)
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_BITBUCKET", _BB_SECRET)
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    "/webhooks/github",
                    content=b'{"action":"opened"}',
                    headers={
                        "x-github-event": "pull_request",
                        "content-type": "application/json",
                    },
                )
                assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_gitlab_no_secret_returns_403(self, monkeypatch):
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITHUB", _GH_SECRET)
        monkeypatch.delenv("MERGEGUARD_WEBHOOK_SECRET_GITLAB", raising=False)
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_BITBUCKET", _BB_SECRET)
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    "/webhooks/gitlab",
                    json={"object_attributes": {"action": "open"}},
                    headers={"x-gitlab-event": "Merge Request Hook"},
                )
                assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_bitbucket_no_secret_returns_403(self, monkeypatch):
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITHUB", _GH_SECRET)
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITLAB", _GL_SECRET)
        monkeypatch.delenv("MERGEGUARD_WEBHOOK_SECRET_BITBUCKET", raising=False)
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    "/webhooks/bitbucket",
                    content=b'{"pullrequest":{}}',
                    headers={
                        "x-event-key": "pullrequest:created",
                        "content-type": "application/json",
                    },
                )
                assert resp.status_code == 403
