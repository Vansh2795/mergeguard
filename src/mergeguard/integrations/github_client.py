"""GitHub API integration for fetching PR data."""

from __future__ import annotations

import httpx
from github import Auth, Github
from github.PullRequest import PullRequest as GHPullRequest

from mergeguard.models import ChangedFile, FileChangeStatus, PRInfo


class GitHubClient:
    """Fetches PR data from GitHub REST API."""

    def __init__(self, token: str, repo_full_name: str):
        """
        Args:
            token: GitHub personal access token or GITHUB_TOKEN
            repo_full_name: "owner/repo" format
        """
        auth = Auth.Token(token)
        self._gh = Github(auth=auth)
        self._repo = self._gh.get_repo(repo_full_name)
        self._http = httpx.Client(
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=30.0,
        )

    def get_open_prs(self, max_count: int = 30) -> list[PRInfo]:
        """Fetch all open PRs with metadata."""
        pulls = self._repo.get_pulls(state="open", sort="updated", direction="desc")
        result: list[PRInfo] = []
        for i, pr in enumerate(pulls):
            if i >= max_count:
                break
            result.append(self._pr_to_info(pr))
        return result

    def get_pr(self, number: int) -> PRInfo:
        """Fetch a single PR."""
        pr = self._repo.get_pull(number)
        return self._pr_to_info(pr)

    def get_pr_files(self, pr_number: int) -> list[ChangedFile]:
        """Fetch the list of files changed in a PR."""
        pr = self._repo.get_pull(pr_number)
        files: list[ChangedFile] = []
        for f in pr.get_files():
            files.append(
                ChangedFile(
                    path=f.filename,
                    status=self._map_status(f.status),
                    additions=f.additions,
                    deletions=f.deletions,
                    patch=f.patch,
                    previous_path=f.previous_filename,
                )
            )
        return files

    def get_pr_diff(self, pr_number: int) -> str:
        """Fetch the full unified diff of a PR."""
        url = f"https://api.github.com/repos/{self._repo.full_name}/pulls/{pr_number}"
        resp = self._http.get(url, headers={"Accept": "application/vnd.github.v3.diff"})
        resp.raise_for_status()
        return resp.text

    def get_file_content(self, path: str, ref: str) -> str | None:
        """Fetch file content at a specific branch/commit."""
        try:
            content = self._repo.get_contents(path, ref=ref)
            if isinstance(content, list):
                return None  # Directory, not a file
            return content.decoded_content.decode("utf-8")
        except Exception:
            return None  # File doesn't exist at this ref

    def post_pr_comment(self, pr_number: int, body: str) -> None:
        """Post or update a MergeGuard comment on a PR."""
        pr = self._repo.get_pull(pr_number)
        # Check for existing MergeGuard comment to update
        marker = "<!-- mergeguard-report -->"
        for comment in pr.get_issue_comments():
            if marker in comment.body:
                comment.edit(f"{marker}\n{body}")
                return
        pr.create_issue_comment(f"{marker}\n{body}")

    def set_commit_status(
        self, sha: str, state: str, description: str, target_url: str = ""
    ) -> None:
        """Set commit status (success/failure/pending/error)."""
        commit = self._repo.get_commit(sha)
        commit.create_status(
            state=state,
            description=description[:140],  # GitHub limit
            target_url=target_url,
            context="mergeguard/cross-pr-analysis",
        )

    # ── Private helpers ──

    def _pr_to_info(self, pr: GHPullRequest) -> PRInfo:
        return PRInfo(
            number=pr.number,
            title=pr.title,
            author=pr.user.login,
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            head_sha=pr.head.sha,
            created_at=pr.created_at,
            updated_at=pr.updated_at,
            labels=[label.name for label in pr.labels],
            description=pr.body or "",
        )

    @staticmethod
    def _map_status(status: str) -> FileChangeStatus:
        mapping = {
            "added": FileChangeStatus.ADDED,
            "modified": FileChangeStatus.MODIFIED,
            "removed": FileChangeStatus.REMOVED,
            "renamed": FileChangeStatus.RENAMED,
        }
        return mapping.get(status, FileChangeStatus.MODIFIED)
