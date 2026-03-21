"""Tests for webhook server — signature verification, event parsing, routes."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from mergeguard.server.events import (
    EventAction,
    parse_bitbucket_event,
    parse_github_event,
    parse_gitlab_event,
)
from mergeguard.server.webhook import (
    verify_bitbucket_signature,
    verify_github_signature,
    verify_gitlab_token,
)


# ── Signature verification ──────────────────────────────────────────


class TestGitHubSignatureVerification:
    def test_valid_signature(self):
        secret = "test-secret"
        payload = b'{"action": "opened"}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_github_signature(payload, sig, secret) is True

    def test_invalid_signature(self):
        assert verify_github_signature(b"payload", "sha256=bad", "secret") is False

    def test_missing_signature(self):
        assert verify_github_signature(b"payload", None, "secret") is False

    def test_wrong_prefix(self):
        assert verify_github_signature(b"payload", "sha1=abc", "secret") is False


class TestGitLabTokenVerification:
    def test_valid_token(self):
        assert verify_gitlab_token("my-secret", "my-secret") is True

    def test_invalid_token(self):
        assert verify_gitlab_token("wrong", "my-secret") is False

    def test_missing_token(self):
        assert verify_gitlab_token(None, "my-secret") is False


class TestBitbucketSignatureVerification:
    def test_valid_signature(self):
        secret = "bb-secret"
        payload = b'{"pullrequest": {}}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_bitbucket_signature(payload, sig, secret) is True

    def test_invalid_signature(self):
        assert verify_bitbucket_signature(b"data", "sha256=nope", "secret") is False


# ── Event parsing ───────────────────────────────────────────────────


class TestGitHubEventParsing:
    def _make_payload(self, action: str = "opened") -> dict:
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

    def test_opened(self):
        event = parse_github_event(
            {"x-github-event": "pull_request"}, self._make_payload("opened")
        )
        assert event is not None
        assert event.action == EventAction.OPENED
        assert event.pr_number == 42
        assert event.repo_full_name == "owner/repo"
        assert event.head_sha == "abc123"

    def test_synchronize(self):
        event = parse_github_event(
            {"x-github-event": "pull_request"}, self._make_payload("synchronize")
        )
        assert event is not None
        assert event.action == EventAction.UPDATED

    def test_closed(self):
        event = parse_github_event(
            {"x-github-event": "pull_request"}, self._make_payload("closed")
        )
        assert event is not None
        assert event.action == EventAction.CLOSED

    def test_ignored_event_type(self):
        event = parse_github_event({"x-github-event": "push"}, {"action": "opened"})
        assert event is None

    def test_ignored_action(self):
        event = parse_github_event(
            {"x-github-event": "pull_request"}, self._make_payload("labeled")
        )
        assert event is None


class TestGitLabEventParsing:
    def _make_payload(self, action: str = "open") -> dict:
        return {
            "object_attributes": {
                "action": action,
                "iid": 10,
                "last_commit": {"id": "def456"},
                "target_branch": "main",
            },
            "project": {"path_with_namespace": "group/project"},
            "user": {"username": "bob"},
        }

    def test_open(self):
        event = parse_gitlab_event(
            {"x-gitlab-event": "Merge Request Hook"}, self._make_payload("open")
        )
        assert event is not None
        assert event.action == EventAction.OPENED
        assert event.pr_number == 10
        assert event.platform == "gitlab"

    def test_update(self):
        event = parse_gitlab_event(
            {"x-gitlab-event": "Merge Request Hook"}, self._make_payload("update")
        )
        assert event is not None
        assert event.action == EventAction.UPDATED

    def test_ignored_event(self):
        event = parse_gitlab_event(
            {"x-gitlab-event": "Push Hook"}, self._make_payload()
        )
        assert event is None


class TestBitbucketEventParsing:
    def _make_payload(self) -> dict:
        return {
            "pullrequest": {
                "id": 7,
                "source": {"commit": {"hash": "ghi789"}},
                "destination": {"branch": {"name": "main"}},
            },
            "repository": {"full_name": "workspace/repo"},
            "actor": {"username": "carol"},
        }

    def test_created(self):
        event = parse_bitbucket_event(
            {"x-event-key": "pullrequest:created"}, self._make_payload()
        )
        assert event is not None
        assert event.action == EventAction.OPENED
        assert event.pr_number == 7
        assert event.platform == "bitbucket"

    def test_updated(self):
        event = parse_bitbucket_event(
            {"x-event-key": "pullrequest:updated"}, self._make_payload()
        )
        assert event is not None
        assert event.action == EventAction.UPDATED

    def test_fulfilled(self):
        event = parse_bitbucket_event(
            {"x-event-key": "pullrequest:fulfilled"}, self._make_payload()
        )
        assert event is not None
        assert event.action == EventAction.CLOSED

    def test_ignored_event(self):
        event = parse_bitbucket_event(
            {"x-event-key": "repo:push"}, self._make_payload()
        )
        assert event is None
