"""Integration tests for GitHub client with mocked API."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx

from mergeguard.integrations.github_client import GitHubClient
from mergeguard.models import FileChangeStatus


def _make_mock_pr(number=1, title="Test PR", login="alice",
                  base_ref="main", head_ref="feature/test", head_sha="abc123",
                  created_at=None, updated_at=None, labels=None, body="desc"):
    """Create a mock PyGithub PullRequest."""
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.user.login = login
    pr.base.ref = base_ref
    pr.head.ref = head_ref
    pr.head.sha = head_sha
    pr.created_at = created_at or datetime(2026, 1, 15)
    pr.updated_at = updated_at or datetime(2026, 1, 16)
    pr.labels = []
    if labels:
        for name in labels:
            label = MagicMock()
            label.name = name
            pr.labels.append(label)
    pr.body = body
    return pr


def _make_mock_file(filename="src/app.py", status="modified",
                    additions=10, deletions=5, patch="@@ -1,5 +1,10 @@\n+new",
                    previous_filename=None):
    """Create a mock PyGithub File."""
    f = MagicMock()
    f.filename = filename
    f.status = status
    f.additions = additions
    f.deletions = deletions
    f.patch = patch
    f.previous_filename = previous_filename
    return f


class TestGitHubClientIntegration:
    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_get_open_prs(self, MockGithub, MockHttpClient):
        mock_repo = MagicMock()
        MockGithub.return_value.get_repo.return_value = mock_repo

        mock_pr1 = _make_mock_pr(number=1, title="First PR")
        mock_pr2 = _make_mock_pr(number=2, title="Second PR", login="bob")
        mock_repo.get_pulls.return_value = [mock_pr1, mock_pr2]

        client = GitHubClient("fake-token", "owner/repo")
        prs = client.get_open_prs(max_count=10)

        assert len(prs) == 2
        assert prs[0].number == 1
        assert prs[0].title == "First PR"
        assert prs[0].author == "alice"
        assert prs[1].number == 2
        assert prs[1].author == "bob"
        mock_repo.get_pulls.assert_called_once_with(
            state="open", sort="updated", direction="desc"
        )

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_get_pr_files(self, MockGithub, MockHttpClient):
        mock_repo = MagicMock()
        MockGithub.return_value.get_repo.return_value = mock_repo

        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_files.return_value = [
            _make_mock_file("src/app.py", "modified", 10, 5),
            _make_mock_file("src/new.py", "added", 50, 0),
        ]

        client = GitHubClient("fake-token", "owner/repo")
        files = client.get_pr_files(42)

        assert len(files) == 2
        assert files[0].path == "src/app.py"
        assert files[0].status == FileChangeStatus.MODIFIED
        assert files[0].additions == 10
        assert files[1].path == "src/new.py"
        assert files[1].status == FileChangeStatus.ADDED

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_get_pr_diff(self, MockGithub, MockHttpClient):
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        MockGithub.return_value.get_repo.return_value = mock_repo

        expected_diff = "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
        mock_response = MagicMock()
        mock_response.text = expected_diff
        mock_response.raise_for_status = MagicMock()
        MockHttpClient.return_value.get.return_value = mock_response

        client = GitHubClient("fake-token", "owner/repo")
        diff = client.get_pr_diff(42)

        assert diff == expected_diff
        MockHttpClient.return_value.get.assert_called_once()

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_post_comment(self, MockGithub, MockHttpClient):
        mock_repo = MagicMock()
        MockGithub.return_value.get_repo.return_value = mock_repo

        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr

        # No existing MergeGuard comment
        mock_pr.get_issue_comments.return_value = []

        client = GitHubClient("fake-token", "owner/repo")
        client.post_pr_comment(42, "Test report body")

        mock_pr.create_issue_comment.assert_called_once()
        call_args = mock_pr.create_issue_comment.call_args[0][0]
        assert "<!-- mergeguard-report -->" in call_args
        assert "Test report body" in call_args

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_post_comment_updates_existing(self, MockGithub, MockHttpClient):
        """When a MergeGuard comment already exists, it should be updated."""
        mock_repo = MagicMock()
        MockGithub.return_value.get_repo.return_value = mock_repo

        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr

        existing_comment = MagicMock()
        existing_comment.body = "<!-- mergeguard-report -->\nOld report"
        mock_pr.get_issue_comments.return_value = [existing_comment]

        client = GitHubClient("fake-token", "owner/repo")
        client.post_pr_comment(42, "Updated report body")

        existing_comment.edit.assert_called_once()
        mock_pr.create_issue_comment.assert_not_called()

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_rate_limit_handling(self, MockGithub, MockHttpClient):
        """When GitHub raises a rate limit error, the exception propagates."""
        from github import GithubException

        mock_repo = MagicMock()
        MockGithub.return_value.get_repo.return_value = mock_repo
        mock_repo.get_pulls.side_effect = GithubException(
            403, {"message": "API rate limit exceeded"}, None
        )

        client = GitHubClient("fake-token", "owner/repo")
        try:
            client.get_open_prs()
            assert False, "Should have raised GithubException"
        except GithubException as e:
            assert e.status == 403
