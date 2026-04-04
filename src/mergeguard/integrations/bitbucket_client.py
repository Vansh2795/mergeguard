"""Bitbucket Cloud API integration for fetching PR data.

Uses Bitbucket Cloud REST API 2.0 via httpx with Basic Auth (App Password).
Method names follow the SCMClient protocol.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from mergeguard.models import ChangedFile, FileChangeStatus, PRInfo

if TYPE_CHECKING:
    from mergeguard.integrations.protocol import ReviewComment

logger = logging.getLogger(__name__)

_PAGE_LEN = 50  # Bitbucket max pagelen


class BitbucketClient:
    """Fetches PR data from Bitbucket Cloud REST API 2.0."""

    def __init__(self, token: str, repo_full_name: str):
        """
        Args:
            token: "username:app_password" format for Basic Auth.
            repo_full_name: "workspace/repo" format.
        """
        if ":" not in token:
            raise ValueError(
                "token must be in 'username:app_password' format for Bitbucket Basic Auth"
            )
        username, app_password = token.split(":", 1)
        self._repo_full_name = repo_full_name
        parts = repo_full_name.split("/", 1)
        if len(parts) != 2:
            raise ValueError("repo_full_name must be in 'workspace/repo' format")
        self._workspace = parts[0]
        self._repo_slug = parts[1]
        self._base_url = (
            f"https://api.bitbucket.org/2.0/repositories/{self._workspace}/{self._repo_slug}"
        )
        self._http = httpx.Client(
            transport=httpx.HTTPTransport(retries=3),
            auth=(username, app_password),
            headers={"Accept": "application/json"},
            timeout=30.0,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> BitbucketClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Public API (SCMClient protocol) ──

    def get_open_prs(self, max_count: int = 200, max_age_days: int | None = None) -> list[PRInfo]:
        """Fetch open pull requests with metadata."""
        logger.debug(
            "Fetching open PRs (max %d, max_age_days=%s) from %s",
            max_count,
            max_age_days,
            self._repo_full_name,
        )
        cutoff: datetime | None = None
        if max_age_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

        # Bitbucket uses q= for filtering and sort= for ordering
        params: dict[str, str | int] = {
            "state": "OPEN",
            "pagelen": min(max_count, _PAGE_LEN),
        }

        result: list[PRInfo] = []
        url: str | None = f"{self._base_url}/pullrequests"

        while url and len(result) < max_count:
            resp = self._get(url, params=params)
            data = resp.json()
            for pr in data.get("values", []):
                if len(result) >= max_count:
                    break
                info = self._pr_to_info(pr)
                # Apply age filter client-side since Bitbucket's query
                # language doesn't always support updated_on filtering well
                if cutoff and info.updated_at < cutoff:
                    continue
                result.append(info)

            # Bitbucket pagination uses "next" URL in the response body
            url = data.get("next")
            # Clear params since the "next" URL already includes them
            params = {}

        return result

    def get_pr(self, number: int) -> PRInfo:
        """Fetch a single pull request by ID."""
        logger.debug("Fetching PR #%d", number)
        resp = self._get(f"{self._base_url}/pullrequests/{number}")
        return self._pr_to_info(resp.json())

    def get_pr_files(self, pr_number: int) -> list[ChangedFile]:
        """Fetch the list of files changed in a pull request via diffstat."""
        logger.debug("Fetching files for PR #%d", pr_number)
        # Get the PR to find the merge spec (source..destination)
        pr_resp = self._get(f"{self._base_url}/pullrequests/{pr_number}")
        pr_data = pr_resp.json()
        source_hash = pr_data.get("source", {}).get("commit", {}).get("hash", "")
        dest_hash = pr_data.get("destination", {}).get("commit", {}).get("hash", "")
        spec = f"{dest_hash}..{source_hash}"

        files: list[ChangedFile] = []
        url: str | None = f"{self._base_url}/diffstat/{spec}"
        params: dict[str, str | int] = {"pagelen": _PAGE_LEN}

        while url:
            resp = self._get(url, params=params)
            data = resp.json()
            for entry in data.get("values", []):
                files.append(self._diffstat_to_changed_file(entry))
            url = data.get("next")
            params = {}

        # Fetch full diff and attach per-file patches for symbol analysis
        try:
            raw_diff = self.get_pr_diff(pr_number)
            patches = _split_diff_by_file(raw_diff)
            for f in files:
                if f.patch is None:
                    f.patch = patches.get(f.path)
        except (httpx.HTTPError, OSError, ValueError):
            logger.debug("Failed to fetch diff for patch attachment", exc_info=True)

        return files

    def get_pr_diff(self, pr_number: int) -> str:
        """Fetch the raw unified diff for a pull request."""
        logger.debug("Fetching diff for PR #%d", pr_number)
        url = f"{self._base_url}/pullrequests/{pr_number}/diff"
        resp = self._http.get(url)
        resp.raise_for_status()
        self._check_rate_limit(resp)
        return resp.text

    def get_file_content(self, path: str, ref: str) -> str | None:
        """Fetch raw file content at a specific ref (commit hash or branch)."""
        logger.debug("Fetching content: %s at %s", path, ref)
        url = f"{self._base_url}/src/{ref}/{path}"
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            self._check_rate_limit(resp)
            return resp.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.debug("File not found: %s at %s", path, ref)
                return None
            raise

    def post_pr_comment(self, pr_number: int, body: str) -> None:
        """Post or update a MergeGuard comment on a pull request."""
        marker = "<!-- mergeguard-report -->"
        comments_url = f"{self._base_url}/pullrequests/{pr_number}/comments"

        # Search existing comments for marker
        url: str | None = comments_url
        params: dict[str, str | int] = {"pagelen": _PAGE_LEN}

        while url:
            resp = self._get(url, params=params)
            self._check_rate_limit(resp)
            data = resp.json()
            for comment in data.get("values", []):
                content = comment.get("content", {}).get("raw", "")
                if marker in content:
                    # Update existing comment
                    comment_id = comment["id"]
                    put_resp = self._http.put(
                        f"{comments_url}/{comment_id}",
                        json={"content": {"raw": f"{marker}\n{body}"}},
                    )
                    put_resp.raise_for_status()
                    return
            url = data.get("next")
            params = {}

        # Create new comment
        post_resp = self._http.post(
            comments_url,
            json={"content": {"raw": f"{marker}\n{body}"}},
        )
        post_resp.raise_for_status()

    def post_pr_review(
        self,
        pr_number: int,
        body: str,
        comments: list[ReviewComment],
        event: str = "COMMENT",
    ) -> None:
        """Post inline comments on a pull request."""
        marker = "<!-- mergeguard-review -->"
        comments_url = f"{self._base_url}/pullrequests/{pr_number}/comments"

        # Delete previous MergeGuard inline comments
        url: str | None = comments_url
        params: dict[str, str | int] = {"pagelen": _PAGE_LEN}
        while url:
            resp = self._get(url, params=params)
            data = resp.json()
            for c in data.get("values", []):
                if marker in c.get("content", {}).get("raw", ""):
                    self._http.delete(f"{comments_url}/{c['id']}")
            url = data.get("next")
            params = {}

        # Post each inline comment
        for comment in comments:
            payload: dict[str, Any] = {
                "content": {"raw": f"{marker}\n{comment.body}"},
                "inline": {"to": comment.line, "path": comment.path},
            }
            self._http.post(comments_url, json=payload).raise_for_status()

    def post_commit_status(
        self,
        sha: str,
        state: str,
        description: str,
        target_url: str = "",
        context: str = "mergeguard/cross-pr-analysis",
    ) -> None:
        """Post a build status on a Bitbucket commit.

        Maps GitHub-style states to Bitbucket states:
        - "pending" → "INPROGRESS"
        - "success" → "SUCCESSFUL"
        - "failure" → "FAILED"
        - "error"   → "FAILED"
        """
        bb_state_map = {
            "pending": "INPROGRESS",
            "success": "SUCCESSFUL",
            "failure": "FAILED",
            "error": "FAILED",
        }
        bb_state = bb_state_map.get(state, "FAILED")

        url = f"{self._base_url}/commit/{sha}/statuses/build"
        payload: dict[str, str] = {
            "state": bb_state,
            "key": context,
            "description": description[:140],
            "url": target_url or "https://github.com/Vansh2795/mergeguard",
        }

        try:
            resp = self._http.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                logger.warning(
                    "Insufficient permissions to post commit status on Bitbucket (%d)",
                    exc.response.status_code,
                )
                return
            raise

    def add_labels(self, pr_number: int, labels: list[str]) -> None:
        """No-op: Bitbucket Cloud does not support PR labels."""
        logger.warning(
            "Bitbucket Cloud does not support PR labels — skipping add_labels(%s, %s)",
            pr_number,
            labels,
        )

    def request_reviewers(self, pr_number: int, reviewers: list[str]) -> None:
        """Request reviewers on a pull request by looking up user UUIDs."""
        url = f"{self._base_url}/pullrequests/{pr_number}"
        resp = self._get(url)
        pr_data = resp.json()

        # Build updated reviewers list
        existing = pr_data.get("reviewers", [])
        existing_uuids = {r.get("uuid") for r in existing if r.get("uuid")}

        new_reviewers = list(existing)
        for username in reviewers:
            username = username.lstrip("@")
            user_url = f"https://api.bitbucket.org/2.0/users/{username}"
            try:
                user_resp = self._get(user_url)
                user_data = user_resp.json()
                if user_data.get("uuid") not in existing_uuids:
                    new_reviewers.append({"uuid": user_data["uuid"]})
            except (httpx.HTTPError, OSError, KeyError):
                logger.warning("Bitbucket user not found: %s", username)

        put_resp = self._http.put(url, json={"reviewers": new_reviewers})
        put_resp.raise_for_status()

    # ── Private helpers ──

    def _get(
        self,
        url: str,
        params: dict[str, str | int] | None = None,
    ) -> httpx.Response:
        """Send GET request with rate-limit handling."""
        resp = self._http.get(url, params=params)
        resp.raise_for_status()
        self._check_rate_limit(resp)
        return resp

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """Sleep if Bitbucket rate limit is nearly exhausted."""
        from mergeguard.integrations.rate_limit import check_rate_limit

        check_rate_limit(
            response,
            remaining_header="X-RateLimit-Remaining",
            reset_header="X-RateLimit-Reset",
        )

    def _pr_to_info(self, pr: dict[str, Any]) -> PRInfo:
        """Convert a Bitbucket PR JSON dict to PRInfo."""
        source = pr.get("source", {})
        destination = pr.get("destination", {})

        # Detect fork: source and destination repos differ
        source_repo = source.get("repository", {}).get("full_name", "")
        dest_repo = destination.get("repository", {}).get("full_name", "")
        is_fork = bool(source_repo and dest_repo and source_repo != dest_repo)

        created_at = _parse_bitbucket_datetime(pr["created_on"])
        updated_at = _parse_bitbucket_datetime(pr["updated_on"])

        head_sha = source.get("commit", {}).get("hash", "")
        author = pr.get("author", {}).get("nickname", "") or pr.get("author", {}).get(
            "display_name", ""
        )

        from mergeguard.models import PRState

        bb_state = pr.get("state", "OPEN").upper()
        if bb_state == "MERGED":
            state = PRState.MERGED
            merged_at = updated_at  # Bitbucket uses updated_on as merge timestamp
            closed_at = updated_at
        elif bb_state == "DECLINED":
            state = PRState.CLOSED
            merged_at = None
            closed_at = updated_at
        else:
            state = PRState.OPEN
            merged_at = None
            closed_at = None

        return PRInfo(
            number=pr["id"],
            title=pr["title"],
            author=author,
            base_branch=destination.get("branch", {}).get("name", ""),
            head_branch=source.get("branch", {}).get("name", ""),
            head_sha=head_sha,
            is_fork=is_fork,
            created_at=created_at,
            updated_at=updated_at,
            state=state,
            merged_at=merged_at,
            closed_at=closed_at,
            labels=[],  # Bitbucket Cloud PRs don't have labels
            description=pr.get("description") or "",
        )

    @staticmethod
    def _diffstat_to_changed_file(entry: dict[str, Any]) -> ChangedFile:
        """Convert a Bitbucket diffstat entry to ChangedFile."""
        status_str = entry.get("status", "modified")
        status_map: dict[str, FileChangeStatus] = {
            "added": FileChangeStatus.ADDED,
            "removed": FileChangeStatus.REMOVED,
            "modified": FileChangeStatus.MODIFIED,
            "renamed": FileChangeStatus.RENAMED,
        }
        status = status_map.get(status_str, FileChangeStatus.MODIFIED)

        lines_added = entry.get("lines_added", 0) or 0
        lines_removed = entry.get("lines_removed", 0) or 0

        new_path = entry.get("new", {})
        old_path = entry.get("old", {})

        # new and old can be None for pure adds/deletes
        path = ""
        if new_path:
            path = new_path.get("path", "")
        elif old_path:
            path = old_path.get("path", "")

        previous_path = None
        if status == FileChangeStatus.RENAMED and old_path:
            previous_path = old_path.get("path")

        return ChangedFile(
            path=path,
            status=status,
            additions=lines_added,
            deletions=lines_removed,
            patch=None,  # Bitbucket diffstat doesn't include patch content
            previous_path=previous_path,
        )


_DIFF_FILE_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)


def _split_diff_by_file(raw_diff: str) -> dict[str, str]:
    """Parse a unified diff into {file_path: patch_content}."""
    patches: dict[str, str] = {}
    matches = list(_DIFF_FILE_RE.finditer(raw_diff))
    for i, match in enumerate(matches):
        file_path = match.group(2)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_diff)
        patches[file_path] = raw_diff[start:end].strip()
    return patches


def _parse_bitbucket_datetime(dt_str: str) -> datetime:
    """Parse a Bitbucket Cloud datetime string to a timezone-aware datetime.

    Bitbucket returns ISO 8601 strings like "2024-01-15T10:30:00.123456+00:00".
    """
    # Handle the common formats Bitbucket returns
    dt_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(dt_str)
