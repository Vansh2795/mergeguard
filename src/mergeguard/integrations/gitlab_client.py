"""GitLab API integration for fetching MR data (V2).

This module mirrors the GitHubClient interface for GitLab merge requests.
Planned for Phase 3 (Weeks 19-20).
"""

from __future__ import annotations

from mergeguard.models import ChangedFile, PRInfo


class GitLabClient:
    """Fetches MR data from GitLab REST API.

    TODO: Implement in Phase 3 (Weeks 19-20).
    """

    def __init__(self, token: str, project_path: str, gitlab_url: str = "https://gitlab.com"):
        """
        Args:
            token: GitLab personal access token.
            project_path: "namespace/project" format.
            gitlab_url: GitLab instance URL.
        """
        self._token = token
        self._project_path = project_path
        self._gitlab_url = gitlab_url
        raise NotImplementedError("GitLab integration is planned for Phase 3 (V2)")

    def get_open_mrs(self, max_count: int = 30) -> list[PRInfo]:
        """Fetch all open merge requests with metadata."""
        raise NotImplementedError

    def get_mr(self, iid: int) -> PRInfo:
        """Fetch a single merge request."""
        raise NotImplementedError

    def get_mr_files(self, mr_iid: int) -> list[ChangedFile]:
        """Fetch the list of files changed in a merge request."""
        raise NotImplementedError

    def get_mr_diff(self, mr_iid: int) -> str:
        """Fetch the full unified diff of a merge request."""
        raise NotImplementedError

    def get_file_content(self, path: str, ref: str) -> str | None:
        """Fetch file content at a specific branch/commit."""
        raise NotImplementedError

    def post_mr_comment(self, mr_iid: int, body: str) -> None:
        """Post or update a MergeGuard comment on a merge request."""
        raise NotImplementedError
