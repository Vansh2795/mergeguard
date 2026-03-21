"""Integration tests for GitHub client with mocked API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from mergeguard.integrations.github_client import GitHubClient
from mergeguard.models import FileChangeStatus


def _make_mock_pr(
    number=1,
    title="Test PR",
    login="alice",
    base_ref="main",
    head_ref="feature/test",
    head_sha="abc123",
    created_at=None,
    updated_at=None,
    labels=None,
    body="desc",
):
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


def _make_mock_file(
    filename="src/app.py",
    status="modified",
    additions=10,
    deletions=5,
    patch="@@ -1,5 +1,10 @@\n+new",
    previous_filename=None,
):
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
    def test_get_open_prs(self, mock_github, mock_http_client):
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

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
        mock_repo.get_pulls.assert_called_once_with(state="open", sort="updated", direction="desc")

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_get_open_prs_age_cutoff(self, mock_github, mock_http_client):
        """PRs older than max_age_days should be excluded."""
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

        now = datetime.now(UTC)
        mock_pr1 = _make_mock_pr(number=1, title="Recent", updated_at=now - timedelta(days=1))
        mock_pr2 = _make_mock_pr(number=2, title="Within range", updated_at=now - timedelta(days=5))
        mock_pr3 = _make_mock_pr(number=3, title="Too old", updated_at=now - timedelta(days=14))
        # PyGithub returns naive UTC datetimes
        mock_pr1.updated_at = (now - timedelta(days=1)).replace(tzinfo=None)
        mock_pr2.updated_at = (now - timedelta(days=5)).replace(tzinfo=None)
        mock_pr3.updated_at = (now - timedelta(days=14)).replace(tzinfo=None)
        mock_repo.get_pulls.return_value = [mock_pr1, mock_pr2, mock_pr3]

        client = GitHubClient("fake-token", "owner/repo")
        prs = client.get_open_prs(max_count=100, max_age_days=7)

        assert len(prs) == 2
        assert prs[0].number == 1
        assert prs[1].number == 2

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_get_open_prs_max_count_caps_before_age(self, mock_github, mock_http_client):
        """max_count should cap results even when all PRs are within age range."""
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

        now = datetime.now(UTC)
        mock_prs = []
        for i in range(5):
            pr = _make_mock_pr(number=i + 1, title=f"PR {i + 1}")
            pr.updated_at = (now - timedelta(days=i)).replace(tzinfo=None)
            mock_prs.append(pr)
        mock_repo.get_pulls.return_value = mock_prs

        client = GitHubClient("fake-token", "owner/repo")
        prs = client.get_open_prs(max_count=3, max_age_days=30)

        assert len(prs) == 3
        assert [p.number for p in prs] == [1, 2, 3]

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_get_pr_files(self, mock_github, mock_http_client):
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

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
    def test_get_pr_diff(self, mock_github, mock_http_client):
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_github.return_value.get_repo.return_value = mock_repo

        expected_diff = (
            "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
        )
        mock_response = MagicMock()
        mock_response.text = expected_diff
        mock_response.raise_for_status = MagicMock()
        mock_http_client.return_value.get.return_value = mock_response

        client = GitHubClient("fake-token", "owner/repo")
        diff = client.get_pr_diff(42)

        assert diff == expected_diff
        mock_http_client.return_value.get.assert_called_once()

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_post_comment(self, mock_github, mock_http_client):
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

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
    def test_post_comment_updates_existing(self, mock_github, mock_http_client):
        """When a MergeGuard comment already exists, it should be updated."""
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

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
    def test_get_file_content_returns_none_on_404(self, mock_github, mock_http_client):
        """UnknownObjectException (404) should return None."""
        from github import UnknownObjectException

        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo
        mock_repo.get_contents.side_effect = UnknownObjectException(
            404, {"message": "Not Found"}, None
        )

        client = GitHubClient("fake-token", "owner/repo")
        result = client.get_file_content("nonexistent.py", "main")
        assert result is None

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_get_file_content_propagates_auth_error(self, mock_github, mock_http_client):
        """BadCredentialsException (401) should propagate, not be swallowed."""
        from github import BadCredentialsException

        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo
        mock_repo.get_contents.side_effect = BadCredentialsException(
            401, {"message": "Bad credentials"}, None
        )

        client = GitHubClient("fake-token", "owner/repo")
        try:
            client.get_file_content("file.py", "main")
            raise AssertionError("Should have raised BadCredentialsException")
        except BadCredentialsException as e:
            assert e.status == 401

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_rate_limit_remaining_property(self, mock_github, mock_http_client):
        """rate_limit_remaining property should return core remaining count."""
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

        mock_rate_limit = MagicMock()
        mock_rate_limit.rate.remaining = 4500
        mock_github.return_value.get_rate_limit.return_value = mock_rate_limit

        client = GitHubClient("fake-token", "owner/repo")
        assert client.rate_limit_remaining == 4500

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_pr_to_info_detects_fork(self, mock_github, mock_http_client):
        """PR from a different repo should be detected as a fork."""
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

        mock_pr = _make_mock_pr(number=10)
        mock_pr.head.repo.full_name = "contributor/repo"
        mock_pr.base.repo.full_name = "owner/repo"

        client = GitHubClient("fake-token", "owner/repo")
        pr_info = client._pr_to_info(mock_pr)

        assert pr_info.is_fork is True

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_pr_to_info_non_fork(self, mock_github, mock_http_client):
        """PR from the same repo should not be detected as a fork."""
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

        mock_pr = _make_mock_pr(number=11)
        mock_pr.head.repo.full_name = "owner/repo"
        mock_pr.base.repo.full_name = "owner/repo"

        client = GitHubClient("fake-token", "owner/repo")
        pr_info = client._pr_to_info(mock_pr)

        assert pr_info.is_fork is False

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_pr_to_info_deleted_fork(self, mock_github, mock_http_client):
        """PR whose head repo is None (deleted fork) should be detected as a fork."""
        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo

        mock_pr = _make_mock_pr(number=12)
        mock_pr.head.repo = None

        client = GitHubClient("fake-token", "owner/repo")
        pr_info = client._pr_to_info(mock_pr)

        assert pr_info.is_fork is True

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_rate_limit_handling(self, mock_github, mock_http_client):
        """When GitHub raises a rate limit error, the exception propagates."""
        from github import GithubException

        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo
        mock_repo.get_pulls.side_effect = GithubException(
            403, {"message": "API rate limit exceeded"}, None
        )

        client = GitHubClient("fake-token", "owner/repo")
        try:
            client.get_open_prs()
            raise AssertionError("Should have raised GithubException")
        except GithubException as e:
            assert e.status == 403

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_post_pr_review(self, mock_github, mock_http_client):
        """post_pr_review calls create_review with correct params."""
        from mergeguard.integrations.protocol import ReviewComment

        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_reviews.return_value = []

        client = GitHubClient("fake-token", "owner/repo")
        comments = [
            ReviewComment(path="src/app.py", line=10, body="Conflict here"),
            ReviewComment(path="src/util.py", line=25, body="Another conflict"),
        ]
        client.post_pr_review(42, "Summary body", comments)

        mock_pr.create_review.assert_called_once()
        call_kwargs = mock_pr.create_review.call_args
        assert "<!-- mergeguard-review -->" in call_kwargs.kwargs.get("body", call_kwargs[1].get("body", ""))

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_post_pr_review_dismisses_previous(self, mock_github, mock_http_client):
        """Previous MergeGuard reviews should be dismissed."""
        from mergeguard.integrations.protocol import ReviewComment

        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr

        old_review = MagicMock()
        old_review.body = "<!-- mergeguard-review -->\nOld review"
        mock_pr.get_reviews.return_value = [old_review]

        client = GitHubClient("fake-token", "owner/repo")
        comments = [ReviewComment(path="a.py", line=1, body="test")]
        client.post_pr_review(42, "New summary", comments)

        old_review.dismiss.assert_called_once_with("Superseded by new MergeGuard analysis")
        mock_pr.create_review.assert_called_once()

    @patch("mergeguard.integrations.github_client.httpx.Client")
    @patch("mergeguard.integrations.github_client.Github")
    def test_post_pr_review_batching(self, mock_github, mock_http_client):
        """Reviews with >50 comments should be batched."""
        from mergeguard.integrations.protocol import ReviewComment

        mock_repo = MagicMock()
        mock_github.return_value.get_repo.return_value = mock_repo
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_reviews.return_value = []

        client = GitHubClient("fake-token", "owner/repo")
        comments = [
            ReviewComment(path=f"f{i}.py", line=i, body=f"Comment {i}")
            for i in range(75)
        ]
        client.post_pr_review(42, "Summary", comments)

        # Should be called twice: first batch of 50, second batch of 25
        assert mock_pr.create_review.call_count == 2
