"""Tests for CLI auto-detection of repo and PR from git state."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import click
import pytest

from mergeguard.cli import _auto_detect_repo, _auto_detect_repo_and_pr
from mergeguard.models import PRInfo


def _make_pr_info(number, branch, updated_at=None):
    return PRInfo(
        number=number,
        title=f"PR {number}",
        author="dev",
        base_branch="main",
        head_branch=branch,
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 1),
        updated_at=updated_at or datetime(2026, 1, 1),
    )


class TestAutoDetectRepoAndPR:
    def test_explicit_values_skip_detection(self):
        """Both --repo and --pr provided — GitLocalClient never instantiated."""
        with patch("mergeguard.integrations.git_local.GitLocalClient") as MockGit:
            repo, pr = _auto_detect_repo_and_pr("owner/repo", 42, "token")

        assert repo == "owner/repo"
        assert pr == 42
        MockGit.assert_not_called()

    @patch("mergeguard.integrations.github_client.GitHubClient")
    def test_auto_detect_repo_from_remote(self, MockGHClient):
        """get_repo_full_name() returns 'owner/repo' — repo populated."""
        mock_git = MagicMock()
        mock_git.get_repo_full_name.return_value = "owner/repo"
        mock_git.get_current_branch.return_value = "feature/auth"

        mock_gh = MagicMock()
        mock_gh.get_open_prs.return_value = [_make_pr_info(10, "feature/auth")]
        MockGHClient.return_value = mock_gh

        with patch("mergeguard.integrations.git_local.GitLocalClient", return_value=mock_git):
            repo, pr = _auto_detect_repo_and_pr(None, None, "token")

        assert repo == "owner/repo"
        assert pr == 10

    def test_auto_detect_pr_from_branch(self):
        """Branch 'feature/auth', one matching PR — pr populated."""
        mock_git = MagicMock()
        mock_git.get_repo_full_name.return_value = "owner/repo"
        mock_git.get_current_branch.return_value = "feature/auth"

        mock_gh = MagicMock()
        mock_gh.get_open_prs.return_value = [
            _make_pr_info(5, "feature/auth"),
        ]

        with patch("mergeguard.integrations.git_local.GitLocalClient", return_value=mock_git):
            with patch("mergeguard.integrations.github_client.GitHubClient", return_value=mock_gh):
                repo, pr = _auto_detect_repo_and_pr(None, None, "token")

        assert pr == 5

    def test_not_git_repo_error(self):
        """GitLocalClient() raises ValueError — click.UsageError."""
        with patch("mergeguard.integrations.git_local.GitLocalClient", side_effect=ValueError("Not a git repo")):
            with pytest.raises(click.UsageError, match="Not in a git repository"):
                _auto_detect_repo_and_pr(None, None, "token")

    def test_default_branch_error(self):
        """Branch is 'main' — click.UsageError with clear message."""
        mock_git = MagicMock()
        mock_git.get_repo_full_name.return_value = "owner/repo"
        mock_git.get_current_branch.return_value = "main"

        with patch("mergeguard.integrations.git_local.GitLocalClient", return_value=mock_git):
            with pytest.raises(click.UsageError, match="Current branch is 'main'"):
                _auto_detect_repo_and_pr(None, None, "token")

    def test_no_matching_pr_error(self):
        """No open PR for branch — click.UsageError."""
        mock_git = MagicMock()
        mock_git.get_repo_full_name.return_value = "owner/repo"
        mock_git.get_current_branch.return_value = "feature/orphan"

        mock_gh = MagicMock()
        mock_gh.get_open_prs.return_value = [
            _make_pr_info(10, "feature/other"),
        ]

        with patch("mergeguard.integrations.git_local.GitLocalClient", return_value=mock_git):
            with patch("mergeguard.integrations.github_client.GitHubClient", return_value=mock_gh):
                with pytest.raises(click.UsageError, match="No open PR found"):
                    _auto_detect_repo_and_pr(None, None, "token")

    def test_multiple_prs_uses_most_recent(self):
        """Two PRs for same branch — most recently updated chosen."""
        mock_git = MagicMock()
        mock_git.get_repo_full_name.return_value = "owner/repo"
        mock_git.get_current_branch.return_value = "feature/shared"

        mock_gh = MagicMock()
        mock_gh.get_open_prs.return_value = [
            _make_pr_info(10, "feature/shared", updated_at=datetime(2026, 1, 1)),
            _make_pr_info(20, "feature/shared", updated_at=datetime(2026, 1, 15)),
        ]

        with patch("mergeguard.integrations.git_local.GitLocalClient", return_value=mock_git):
            with patch("mergeguard.integrations.github_client.GitHubClient", return_value=mock_gh):
                repo, pr = _auto_detect_repo_and_pr(None, None, "token")

        assert pr == 20

    def test_no_token_error(self):
        """Token is None, pr is None — click.UsageError."""
        mock_git = MagicMock()
        mock_git.get_repo_full_name.return_value = "owner/repo"
        mock_git.get_current_branch.return_value = "feature/auth"

        with patch("mergeguard.integrations.git_local.GitLocalClient", return_value=mock_git):
            with pytest.raises(click.UsageError, match="GitHub token is required"):
                _auto_detect_repo_and_pr(None, None, None)


class TestAutoDetectRepo:
    def test_explicit_repo_returned(self):
        """When --repo is provided, return it directly."""
        result = _auto_detect_repo("owner/repo")
        assert result == "owner/repo"

    def test_auto_detect_from_git(self):
        """Auto-detect repo from git remote."""
        mock_git = MagicMock()
        mock_git.get_repo_full_name.return_value = "owner/repo"

        with patch("mergeguard.integrations.git_local.GitLocalClient", return_value=mock_git):
            result = _auto_detect_repo(None)

        assert result == "owner/repo"

    def test_not_git_repo_error(self):
        """Not in a git repo — click.UsageError."""
        with patch("mergeguard.integrations.git_local.GitLocalClient", side_effect=ValueError("Not a git repo")):
            with pytest.raises(click.UsageError, match="Not in a git repository"):
                _auto_detect_repo(None)
