"""Tests for commit status posting across platforms."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

httpx = pytest.importorskip("httpx", reason="httpx not installed")


# ── GitHub ──────────────────────────────────────────────────────────


class TestGitHubCommitStatus:
    def test_posts_with_correct_context(self):
        with patch("mergeguard.integrations.github_client.Github") as mock_github:
            mock_gh = mock_github.return_value
            mock_repo = MagicMock()
            mock_gh.get_repo.return_value = mock_repo
            mock_commit = MagicMock()
            mock_repo.get_commit.return_value = mock_commit

            from mergeguard.integrations.github_client import GitHubClient

            client = GitHubClient.__new__(GitHubClient)
            client._repo = mock_repo

            client.post_commit_status(
                sha="abc123",
                state="success",
                description="No conflicts",
                context="mergeguard/test",
            )

            mock_repo.get_commit.assert_called_once_with("abc123")
            mock_commit.create_status.assert_called_once_with(
                state="success",
                description="No conflicts",
                target_url="",
                context="mergeguard/test",
            )

    def test_description_truncated_to_140(self):
        with patch("mergeguard.integrations.github_client.Github") as mock_github:
            mock_gh = mock_github.return_value
            mock_repo = MagicMock()
            mock_gh.get_repo.return_value = mock_repo
            mock_commit = MagicMock()
            mock_repo.get_commit.return_value = mock_commit

            from mergeguard.integrations.github_client import GitHubClient

            client = GitHubClient.__new__(GitHubClient)
            client._repo = mock_repo

            long_desc = "x" * 200
            client.post_commit_status(sha="abc", state="failure", description=long_desc)

            call_args = mock_commit.create_status.call_args
            assert len(call_args.kwargs["description"]) == 140


# ── GitLab ──────────────────────────────────────────────────────────


class TestGitLabCommitStatus:
    def test_state_mapping_failure_to_failed(self):
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_response

        from mergeguard.integrations.gitlab_client import GitLabClient

        client = GitLabClient.__new__(GitLabClient)
        client._base_url = "https://gitlab.com/api/v4/projects/test%2Frepo"
        client._http = mock_http

        client.post_commit_status(
            sha="def456",
            state="failure",
            description="Conflicts detected",
            context="mergeguard/test",
        )

        call_args = mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["state"] == "failed"
        assert payload["name"] == "mergeguard/test"

    def test_graceful_on_403(self):
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        mock_http.post.return_value = mock_response

        from mergeguard.integrations.gitlab_client import GitLabClient

        client = GitLabClient.__new__(GitLabClient)
        client._base_url = "https://gitlab.com/api/v4/projects/test%2Frepo"
        client._http = mock_http

        # Should not raise
        client.post_commit_status(
            sha="def456", state="success", description="OK"
        )


# ── Bitbucket ───────────────────────────────────────────────────────


class TestBitbucketCommitStatus:
    def test_state_mapping_pending_to_inprogress(self):
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_response

        from mergeguard.integrations.bitbucket_client import BitbucketClient

        client = BitbucketClient.__new__(BitbucketClient)
        client._base_url = "https://api.bitbucket.org/2.0/repositories/ws/repo"
        client._http = mock_http

        client.post_commit_status(
            sha="ghi789",
            state="pending",
            description="Analyzing...",
            context="mergeguard/test",
        )

        call_args = mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["state"] == "INPROGRESS"
        assert payload["key"] == "mergeguard/test"

    def test_state_mapping_success(self):
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_response

        from mergeguard.integrations.bitbucket_client import BitbucketClient

        client = BitbucketClient.__new__(BitbucketClient)
        client._base_url = "https://api.bitbucket.org/2.0/repositories/ws/repo"
        client._http = mock_http

        client.post_commit_status(
            sha="ghi789", state="success", description="OK"
        )

        call_args = mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["state"] == "SUCCESSFUL"

    def test_state_mapping_failure(self):
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_response

        from mergeguard.integrations.bitbucket_client import BitbucketClient

        client = BitbucketClient.__new__(BitbucketClient)
        client._base_url = "https://api.bitbucket.org/2.0/repositories/ws/repo"
        client._http = mock_http

        client.post_commit_status(
            sha="ghi789", state="failure", description="Blocked"
        )

        call_args = mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["state"] == "FAILED"

    def test_graceful_on_401(self):
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        mock_http.post.return_value = mock_response

        from mergeguard.integrations.bitbucket_client import BitbucketClient

        client = BitbucketClient.__new__(BitbucketClient)
        client._base_url = "https://api.bitbucket.org/2.0/repositories/ws/repo"
        client._http = mock_http

        # Should not raise
        client.post_commit_status(
            sha="ghi789", state="success", description="OK"
        )
