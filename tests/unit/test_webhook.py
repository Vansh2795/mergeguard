"""Tests for webhook server — signature verification, event parsing, routes."""

from __future__ import annotations

import hashlib
import hmac

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed (server extras)")

from mergeguard.server.events import (  # noqa: E402
    EventAction,
    MergeGroupEvent,
    parse_bitbucket_event,
    parse_github_event,
    parse_gitlab_event,
)
from mergeguard.server.webhook import (  # noqa: E402
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
        event = parse_github_event({"x-github-event": "pull_request"}, self._make_payload("opened"))
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
        event = parse_github_event({"x-github-event": "pull_request"}, self._make_payload("closed"))
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


class TestMergeGroupEventParsing:
    def _make_payload(self, action: str = "checks_requested") -> dict:
        return {
            "action": action,
            "merge_group": {
                "head_sha": "merge123",
                "base_ref": "refs/heads/main",
                "head_ref": "refs/heads/gh-readonly-queue/main/pr-42-abc",
                "head_commit": {
                    "message": "Merge pull request #42 from feature-branch",
                },
            },
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "github-merge-queue[bot]"},
        }

    def test_checks_requested_parsed(self):
        event = parse_github_event(
            {"x-github-event": "merge_group"}, self._make_payload()
        )
        assert event is not None
        assert isinstance(event, MergeGroupEvent)
        assert event.action == EventAction.MERGE_GROUP_CHECKS_REQUESTED
        assert event.repo_full_name == "owner/repo"
        assert event.head_sha == "merge123"
        assert event.base_branch == "main"

    def test_destroyed_action_returns_none(self):
        event = parse_github_event(
            {"x-github-event": "merge_group"}, self._make_payload("destroyed")
        )
        assert event is None

    def test_pr_numbers_extracted_from_head_ref(self):
        event = parse_github_event(
            {"x-github-event": "merge_group"}, self._make_payload()
        )
        assert isinstance(event, MergeGroupEvent)
        assert 42 in event.pr_numbers

    def test_pr_numbers_extracted_from_commit_message(self):
        payload = self._make_payload()
        payload["merge_group"]["head_ref"] = "refs/heads/gh-readonly-queue/main/entry"
        payload["merge_group"]["head_commit"]["message"] = "Merge #99 and #100"
        event = parse_github_event(
            {"x-github-event": "merge_group"}, payload
        )
        assert isinstance(event, MergeGroupEvent)
        assert 99 in event.pr_numbers
        assert 100 in event.pr_numbers

    def test_missing_merge_group_payload_returns_none(self):
        payload = {
            "action": "checks_requested",
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "bot"},
        }
        event = parse_github_event(
            {"x-github-event": "merge_group"}, payload
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
        event = parse_gitlab_event({"x-gitlab-event": "Push Hook"}, self._make_payload())
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
        event = parse_bitbucket_event({"x-event-key": "pullrequest:created"}, self._make_payload())
        assert event is not None
        assert event.action == EventAction.OPENED
        assert event.pr_number == 7
        assert event.platform == "bitbucket"

    def test_updated(self):
        event = parse_bitbucket_event({"x-event-key": "pullrequest:updated"}, self._make_payload())
        assert event is not None
        assert event.action == EventAction.UPDATED

    def test_fulfilled(self):
        event = parse_bitbucket_event(
            {"x-event-key": "pullrequest:fulfilled"}, self._make_payload()
        )
        assert event is not None
        assert event.action == EventAction.CLOSED

    def test_ignored_event(self):
        event = parse_bitbucket_event({"x-event-key": "repo:push"}, self._make_payload())
        assert event is None
