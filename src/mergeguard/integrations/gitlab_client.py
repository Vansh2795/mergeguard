"""GitLab API integration for fetching MR data.

Uses GitLab REST API v4 via httpx (no python-gitlab dependency).
Method names follow the SCMClient protocol (get_pr, not get_mr).
"""

from __future__ import annotations

import logging
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from mergeguard.models import ChangedFile, FileChangeStatus, PRInfo

if TYPE_CHECKING:
    from mergeguard.integrations.protocol import ReviewComment

logger = logging.getLogger(__name__)

_PER_PAGE = 100


class GitLabClient:
    """Fetches MR data from GitLab REST API v4."""

    def __init__(
        self,
        token: str,
        project_path: str,
        gitlab_url: str = "https://gitlab.com",
    ):
        """
        Args:
            token: GitLab personal access token.
            project_path: "namespace/project" format.
            gitlab_url: GitLab instance URL (no trailing slash).
        """
        self._token = token
        self._project_path = project_path
        self._gitlab_url = gitlab_url.rstrip("/")
        self._encoded_project = urllib.parse.quote(project_path, safe="")
        self._base_url = f"{self._gitlab_url}/api/v4/projects/{self._encoded_project}"
        self._http = httpx.Client(
            transport=httpx.HTTPTransport(retries=3),
            headers={
                "PRIVATE-TOKEN": token,
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST with rate limit awareness."""
        resp = self._http.post(url, **kwargs)
        self._check_rate_limit(resp)
        return resp

    def _put(self, url: str, **kwargs: Any) -> httpx.Response:
        """PUT with rate limit awareness."""
        resp = self._http.put(url, **kwargs)
        self._check_rate_limit(resp)
        return resp

    def __enter__(self) -> GitLabClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Public API (SCMClient protocol) ──

    def get_open_prs(self, max_count: int = 200, max_age_days: int | None = None) -> list[PRInfo]:
        """Fetch open merge requests with metadata."""
        logger.debug(
            "Fetching open MRs (max %d, max_age_days=%s) from %s",
            max_count,
            max_age_days,
            self._project_path,
        )
        params: dict[str, str | int] = {
            "state": "opened",
            "order_by": "updated_at",
            "sort": "desc",
            "per_page": min(max_count, _PER_PAGE),
        }
        if max_age_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
            params["updated_after"] = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        result: list[PRInfo] = []
        url: str | None = f"{self._base_url}/merge_requests"

        while url and len(result) < max_count:
            resp = self._get(url, params=params)
            mrs = resp.json()
            for mr in mrs:
                if len(result) >= max_count:
                    break
                result.append(self._mr_to_info(mr))
            # Pagination: use x-next-page header
            next_page = resp.headers.get("x-next-page", "")
            if next_page:
                params["page"] = int(next_page)
            else:
                break

        return result

    def get_pr(self, number: int) -> PRInfo:
        """Fetch a single merge request by IID."""
        logger.debug("Fetching MR !%d", number)
        resp = self._get(f"{self._base_url}/merge_requests/{number}")
        return self._mr_to_info(resp.json())

    def get_pr_files(self, pr_number: int) -> list[ChangedFile]:
        """Fetch the list of files changed in a merge request."""
        logger.debug("Fetching files for MR !%d", pr_number)
        diffs = self._get_all_diffs(pr_number)
        files: list[ChangedFile] = []
        for d in diffs:
            files.append(self._diff_to_changed_file(d))
        return files

    def get_pr_diff(self, pr_number: int) -> str:
        """Reassemble a unified diff from the MR diffs endpoint."""
        logger.debug("Fetching diff for MR !%d", pr_number)
        diffs = self._get_all_diffs(pr_number)
        segments: list[str] = []
        for d in diffs:
            old_path = d.get("old_path", d["new_path"])
            new_path = d["new_path"]
            diff_text = d.get("diff", "")
            if not diff_text:
                continue
            segment = (
                f"diff --git a/{old_path} b/{new_path}\n"
                f"--- a/{old_path}\n"
                f"+++ b/{new_path}\n"
                f"{diff_text}"
            )
            segments.append(segment)
        return "\n".join(segments)

    def get_file_content(self, path: str, ref: str) -> str | None:
        """Fetch raw file content at a specific ref."""
        logger.debug("Fetching content: %s at %s", path, ref)
        encoded_path = urllib.parse.quote(path, safe="")
        url = f"{self._base_url}/repository/files/{encoded_path}/raw"
        try:
            resp = self._get(url, params={"ref": ref})
            return resp.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.debug("File not found: %s at %s", path, ref)
                return None
            raise

    def post_pr_comment(self, pr_number: int, body: str) -> None:
        """Post or update a MergeGuard note on a merge request."""
        marker = "<!-- mergeguard-report -->"
        notes_url = f"{self._base_url}/merge_requests/{pr_number}/notes"

        # Search existing notes for marker
        resp = self._get(notes_url, params={"per_page": 100, "sort": "desc"})
        self._check_rate_limit(resp)
        for note in resp.json():
            if marker in note.get("body", ""):
                # Update existing note
                note_id = note["id"]
                put_resp = self._put(
                    f"{notes_url}/{note_id}",
                    json={"body": f"{marker}\n{body}"},
                )
                put_resp.raise_for_status()
                return

        # Create new note
        post_resp = self._post(notes_url, json={"body": f"{marker}\n{body}"})
        post_resp.raise_for_status()

    def post_pr_review(
        self,
        pr_number: int,
        body: str,
        comments: list[ReviewComment],
        event: str = "COMMENT",
    ) -> None:
        """Post inline discussions on a merge request."""
        marker = "<!-- mergeguard-review -->"

        # Resolve previous MergeGuard discussions
        notes_url = f"{self._base_url}/merge_requests/{pr_number}/discussions"
        resp = self._get(notes_url, params={"per_page": 100})
        for disc in resp.json():
            for note in disc.get("notes", []):
                if marker in note.get("body", ""):
                    self._put(
                        f"{notes_url}/{disc['id']}",
                        json={"resolved": True},
                    )
                    break

        # Get MR metadata for position info
        mr_resp = self._get(f"{self._base_url}/merge_requests/{pr_number}")
        mr = mr_resp.json()
        diff_refs = mr.get("diff_refs", {})

        # Post each comment as a new discussion with position
        for comment in comments:
            position: dict[str, str | int] = {
                "position_type": "text",
                "base_sha": diff_refs.get("base_sha", ""),
                "head_sha": diff_refs.get("head_sha", ""),
                "start_sha": diff_refs.get("start_sha", ""),
                "new_path": comment.path,
                "old_path": comment.path,
                "new_line": comment.line,
            }
            disc_body = f"{marker}\n{comment.body}"
            self._post(
                notes_url,
                json={"body": disc_body, "position": position},
            ).raise_for_status()

        # Post summary as a regular note
        summary_url = f"{self._base_url}/merge_requests/{pr_number}/notes"
        self._post(summary_url, json={"body": f"{marker}\n{body}"}).raise_for_status()

    def post_commit_status(
        self,
        sha: str,
        state: str,
        description: str,
        target_url: str = "",
        context: str = "mergeguard/cross-pr-analysis",
    ) -> None:
        """Post a commit status via GitLab pipeline status API.

        Maps GitHub-style states to GitLab states:
        - "failure" → "failed"
        - "pending", "success", "error" → passed through as-is
        """
        gitlab_state_map = {"failure": "failed"}
        gl_state = gitlab_state_map.get(state, state)

        url = f"{self._base_url}/statuses/{sha}"
        payload: dict[str, str] = {
            "state": gl_state,
            "description": description[:140],
            "name": context,
        }
        if target_url:
            payload["target_url"] = target_url

        try:
            resp = self._post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                logger.warning(
                    "Insufficient permissions to post commit status on GitLab (%d)",
                    exc.response.status_code,
                )
                return
            raise

    def add_labels(self, pr_number: int, labels: list[str]) -> None:
        """Add labels to a merge request (merges with existing labels)."""
        url = f"{self._base_url}/merge_requests/{pr_number}"
        resp = self._get(url)
        current_labels: list[str] = resp.json().get("labels", [])
        merged = sorted(set(current_labels) | set(labels))
        put_resp = self._put(url, json={"labels": ",".join(merged)})
        put_resp.raise_for_status()

    def request_reviewers(self, pr_number: int, reviewers: list[str]) -> None:
        """Request reviewers on a merge request by username."""
        url = f"{self._base_url}/merge_requests/{pr_number}"
        # Look up user IDs by username
        reviewer_ids: list[int] = []
        for username in reviewers:
            username = username.lstrip("@")
            user_url = f"{self._gitlab_url}/api/v4/users"
            resp = self._get(user_url, params={"username": username})
            users = resp.json()
            if users:
                reviewer_ids.append(users[0]["id"])
            else:
                logger.warning("GitLab user not found: %s", username)
        if reviewer_ids:
            put_resp = self._put(
                url,
                json={"reviewer_ids": reviewer_ids},
            )
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
        """Sleep if GitLab rate limit is nearly exhausted."""
        from mergeguard.integrations.rate_limit import check_rate_limit

        check_rate_limit(
            response,
            remaining_header="RateLimit-Remaining",
            reset_header="RateLimit-Reset",
        )

    def _get_all_diffs(self, mr_iid: int) -> list[dict[str, Any]]:
        """Fetch all diff entries for an MR, handling pagination."""
        url = f"{self._base_url}/merge_requests/{mr_iid}/diffs"
        params: dict[str, str | int] = {"per_page": _PER_PAGE}
        all_diffs: list[dict[str, Any]] = []

        while True:
            resp = self._get(url, params=params)
            all_diffs.extend(resp.json())
            next_page = resp.headers.get("x-next-page", "")
            if next_page:
                params["page"] = int(next_page)
            else:
                break

        return all_diffs

    def _mr_to_info(self, mr: dict[str, Any]) -> PRInfo:
        """Convert a GitLab MR JSON dict to PRInfo."""
        is_fork = mr.get("source_project_id") != mr.get("target_project_id")

        created_at = datetime.fromisoformat(mr["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(mr["updated_at"].replace("Z", "+00:00"))

        labels = mr.get("labels", [])

        from mergeguard.models import PRState

        mr_state_str = mr.get("state", "opened")
        if mr_state_str == "merged":
            state = PRState.MERGED
        elif mr_state_str == "closed":
            state = PRState.CLOSED
        else:
            state = PRState.OPEN

        merged_at = None
        if mr.get("merged_at"):
            merged_at = datetime.fromisoformat(mr["merged_at"].replace("Z", "+00:00"))
        closed_at = None
        if mr.get("closed_at"):
            closed_at = datetime.fromisoformat(mr["closed_at"].replace("Z", "+00:00"))

        return PRInfo(
            number=mr["iid"],
            title=mr["title"],
            author=mr["author"]["username"],
            base_branch=mr["target_branch"],
            head_branch=mr["source_branch"],
            head_sha=mr.get("sha", mr.get("diff_refs", {}).get("head_sha", "")),
            is_fork=is_fork,
            created_at=created_at,
            updated_at=updated_at,
            state=state,
            merged_at=merged_at,
            closed_at=closed_at,
            labels=labels,
            description=mr.get("description") or "",
        )

    @staticmethod
    def _diff_to_changed_file(d: dict[str, Any]) -> ChangedFile:
        """Convert a GitLab diff entry to ChangedFile."""
        if d.get("new_file"):
            status = FileChangeStatus.ADDED
        elif d.get("deleted_file"):
            status = FileChangeStatus.REMOVED
        elif d.get("renamed_file"):
            status = FileChangeStatus.RENAMED
        else:
            status = FileChangeStatus.MODIFIED

        diff_text = d.get("diff", "")
        diff_lines = diff_text.splitlines()
        additions = sum(
            1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
        )

        # Extract patch (hunk headers + diff lines, without the diff --git header)
        patch = _extract_patch_from_diff(diff_text) if diff_text else None

        previous_path = d.get("old_path") if d.get("renamed_file") else None

        return ChangedFile(
            path=d["new_path"],
            status=status,
            additions=additions,
            deletions=deletions,
            patch=patch,
            previous_path=previous_path,
        )


def _extract_patch_from_diff(diff_text: str) -> str | None:
    """Extract hunk-level patch from a GitLab diff field.

    The diff field from GitLab already starts at the hunk headers (@@),
    so we return it as-is if non-empty.
    """
    if not diff_text or not diff_text.strip():
        return None
    return diff_text
