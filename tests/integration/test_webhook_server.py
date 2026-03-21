"""Integration tests for the webhook server — full end-to-end with httpx TestClient."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed (server extras)")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from mergeguard.server.webhook import app, lifespan  # noqa: E402


@pytest.fixture
def _no_webhook_secrets(monkeypatch):
    """Clear webhook secrets so signature checks are skipped."""
    monkeypatch.delenv("MERGEGUARD_WEBHOOK_SECRET_GITHUB", raising=False)
    monkeypatch.delenv("MERGEGUARD_WEBHOOK_SECRET_GITLAB", raising=False)
    monkeypatch.delenv("MERGEGUARD_WEBHOOK_SECRET_BITBUCKET", raising=False)


@pytest.fixture
async def client(_no_webhook_secrets):
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
        resp = await client.post(
            "/webhooks/github",
            json=self._github_payload("opened"),
            headers={"x-github-event": "pull_request"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
        assert resp.json()["pr"] == 42

    @pytest.mark.asyncio
    async def test_push_event_ignored(self, client):
        resp = await client.post(
            "/webhooks/github",
            json={"ref": "refs/heads/main"},
            headers={"x-github-event": "push"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, client, monkeypatch):
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITHUB", "real-secret")
        resp = await client.post(
            "/webhooks/github",
            content=json.dumps(self._github_payload()).encode(),
            headers={
                "x-github-event": "pull_request",
                "x-hub-signature-256": "sha256=invalid",
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self, client, monkeypatch):
        secret = "test-secret"
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITHUB", secret)
        payload = json.dumps(self._github_payload()).encode()
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
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
            headers={"x-gitlab-event": "Merge Request Hook"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, client, monkeypatch):
        monkeypatch.setenv("MERGEGUARD_WEBHOOK_SECRET_GITLAB", "real-token")
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
        resp = await client.post(
            "/webhooks/bitbucket",
            json=self._bb_payload(),
            headers={"x-event-key": "pullrequest:created"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_push_event_ignored(self, client):
        resp = await client.post(
            "/webhooks/bitbucket",
            json={"push": {}},
            headers={"x-event-key": "repo:push"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
