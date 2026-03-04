"""Tests that both clients satisfy the SCMClient protocol."""
from __future__ import annotations

from mergeguard.integrations.protocol import SCMClient


class TestProtocolCompliance:
    def test_github_client_satisfies_protocol(self):
        """GitHubClient should be recognized as an SCMClient."""
        from mergeguard.integrations.github_client import GitHubClient

        assert issubclass(GitHubClient, SCMClient)

    def test_gitlab_client_satisfies_protocol(self):
        """GitLabClient should be recognized as an SCMClient."""
        from mergeguard.integrations.gitlab_client import GitLabClient

        assert issubclass(GitLabClient, SCMClient)
