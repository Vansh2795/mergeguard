"""GitHub API integration for fetching PR data."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
from github import Auth, Github, GithubException, UnknownObjectException
from github.GithubRetry import GithubRetry

from mergeguard.models import ChangedFile, FileChangeStatus, PRInfo

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from github.PullRequest import PullRequest as GHPullRequest

    from mergeguard.integrations.protocol import ReviewComment


class GitHubClient:
    """Fetches PR data from GitHub REST API."""

    def __init__(
        self,
        token: str,
        repo_full_name: str,
        base_url: str | None = None,
        timeout: int = 30,
    ):
        """
        Args:
            token: GitHub personal access token or GITHUB_TOKEN
            repo_full_name: "owner/repo" format
            base_url: GitHub Enterprise Server URL (e.g., https://github.example.com).
                      When set, API calls go to {base_url}/api/v3.
            timeout: HTTP timeout in seconds.
        """
        self._token = token
        self._base_url = base_url
        auth = Auth.Token(token)
        retry = GithubRetry(secondary_rate_wait=60)
        gh_kwargs: dict[str, object] = {"auth": auth, "retry": retry}
        if base_url:
            # PyGithub expects base_url to end with /api/v3
            api_url = base_url.rstrip("/")
            if not api_url.endswith("/api/v3"):
                api_url = f"{api_url}/api/v3"
            gh_kwargs["base_url"] = api_url
        self._gh = Github(**gh_kwargs)  # type: ignore[arg-type]
        self._repo = self._gh.get_repo(repo_full_name)
        self._api_base = f"{base_url.rstrip('/')}/api/v3" if base_url else "https://api.github.com"
        self._http = httpx.Client(
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=float(timeout),
        )

    def get_open_prs(self, max_count: int = 200, max_age_days: int | None = None) -> list[PRInfo]:
        """Fetch open PRs with metadata, filtered by age and capped by count.

        Args:
            max_count: Safety cap on number of PRs to return.
            max_age_days: Only return PRs updated within this many days.
                When None, no age filtering is applied.
        """
        logger.debug(
            "Fetching open PRs (max %d, max_age_days=%s) from %s",
            max_count,
            max_age_days,
            self._repo.full_name,
        )
        pulls = self._repo.get_pulls(state="open", sort="updated", direction="desc")

        cutoff = None
        if max_age_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

        result: list[PRInfo] = []
        for i, pr in enumerate(pulls):
            if i >= max_count:
                break
            # PyGithub returns naive datetimes in UTC
            if (
                cutoff is not None
                and pr.updated_at is not None
                and pr.updated_at.replace(tzinfo=UTC) < cutoff
            ):
                break  # PRs are sorted by updated desc — all remaining are older
            result.append(self._pr_to_info(pr))
        return result

    def get_pr(self, number: int) -> PRInfo:
        """Fetch a single PR."""
        logger.debug("Fetching PR #%d", number)
        pr = self._repo.get_pull(number)
        return self._pr_to_info(pr)

    def get_pr_files(self, pr_number: int) -> list[ChangedFile]:
        """Fetch the list of files changed in a PR."""
        logger.debug("Fetching files for PR #%d", pr_number)
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
        logger.debug("Fetching diff for PR #%d", pr_number)
        url = f"{self._api_base}/repos/{self._repo.full_name}/pulls/{pr_number}"
        resp = self._http.get(
            url,
            headers={
                "Accept": "application/vnd.github.v3.diff",
                "Authorization": f"token {self._token}",
            },
        )
        resp.raise_for_status()
        self._check_httpx_rate_limit(resp)
        return resp.text

    def get_file_content(self, path: str, ref: str) -> str | None:
        """Fetch file content at a specific branch/commit."""
        logger.debug("Fetching content: %s at %s", path, ref)
        try:
            content = self._repo.get_contents(path, ref=ref)
            if isinstance(content, list):
                return None  # Directory, not a file
            return content.decoded_content.decode("utf-8")
        except UnicodeDecodeError:
            logger.debug("Binary file (not UTF-8): %s at %s", path, ref)
            return None
        except UnknownObjectException:
            logger.debug("File not found: %s at %s", path, ref)
            return None  # File doesn't exist at this ref
        except GithubException as e:
            if e.status == 404:
                logger.debug("Ref not found: %s at %s", path, ref)
                return None
            raise

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

    def post_pr_review(
        self,
        pr_number: int,
        body: str,
        comments: list[ReviewComment],
        event: str = "COMMENT",
    ) -> None:
        """Post a review with inline comments on a PR."""
        pr = self._repo.get_pull(pr_number)

        # Dismiss previous MergeGuard review if exists
        marker = "<!-- mergeguard-review -->"
        for review in pr.get_reviews():
            if marker in (review.body or ""):
                review.dismiss("Superseded by new MergeGuard analysis")

        # GitHub limits ~60 comments per review — batch if needed
        from github.PullRequest import ReviewComment as GHReviewComment

        batch_size = 50
        gh_comments: list[GHReviewComment] = [
            GHReviewComment(path=c.path, line=c.line, body=c.body, side=c.side)
            for c in comments
        ]

        # First batch creates the review with body
        first_batch = gh_comments[:batch_size]
        pr.create_review(
            body=f"{marker}\n{body}",
            event=event,
            comments=first_batch,
        )

        # Subsequent batches as additional reviews (rare — >50 conflicts)
        for i in range(batch_size, len(gh_comments), batch_size):
            batch = gh_comments[i : i + batch_size]
            pr.create_review(
                body=f"{marker}\n*(continued)*",
                event="COMMENT",
                comments=batch,
            )

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

    @property
    def rate_limit_remaining(self) -> int:
        """Current remaining API rate limit."""
        return self._gh.get_rate_limit().rate.remaining

    # ── Private helpers ──

    def _check_httpx_rate_limit(self, response: httpx.Response) -> None:
        """Sleep if rate limit nearly exhausted."""
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) < 10:
            reset_ts = response.headers.get("X-RateLimit-Reset")
            if reset_ts:
                wait = max(0, int(reset_ts) - int(time.time()) + 1)
                if wait > 0:
                    logger.warning("Rate limit low (%s remaining), sleeping %ds", remaining, wait)
                    time.sleep(min(wait, 300))

    def _pr_to_info(self, pr: GHPullRequest) -> PRInfo:
        is_fork = False
        try:
            if pr.head.repo is None or pr.head.repo.full_name != pr.base.repo.full_name:
                is_fork = True
        except Exception:
            is_fork = True  # Conservative: assume fork if we can't tell

        now = datetime.now(UTC)
        created = pr.created_at if pr.created_at is not None else now
        updated = pr.updated_at if pr.updated_at is not None else now
        return PRInfo(
            number=pr.number,
            title=pr.title,
            author=pr.user.login,
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            head_sha=pr.head.sha,
            is_fork=is_fork,
            created_at=created,
            updated_at=updated,
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
