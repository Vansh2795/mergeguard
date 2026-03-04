"""GitLab API integration for fetching MR data.

Uses GitLab REST API v4 via httpx (no python-gitlab dependency).
Method names follow the SCMClient protocol (get_pr, not get_mr).
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from mergeguard.models import ChangedFile, FileChangeStatus, PRInfo

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
            headers={
                "PRIVATE-TOKEN": token,
                "Accept": "application/json",
            },
            timeout=30.0,
        )

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
                put_resp = self._http.put(
                    f"{notes_url}/{note_id}",
                    json={"body": f"{marker}\n{body}"},
                )
                put_resp.raise_for_status()
                return

        # Create new note
        post_resp = self._http.post(notes_url, json={"body": f"{marker}\n{body}"})
        post_resp.raise_for_status()

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
        remaining = response.headers.get("RateLimit-Remaining")
        if remaining is not None and int(remaining) < 10:
            reset_ts = response.headers.get("RateLimit-Reset")
            if reset_ts:
                wait = max(0, int(reset_ts) - int(time.time()) + 1)
                if wait > 0:
                    logger.warning(
                        "Rate limit low (%s remaining), sleeping %ds",
                        remaining,
                        wait,
                    )
                    time.sleep(min(wait, 300))

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
        additions = sum(
            1
            for line in diff_text.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1
            for line in diff_text.splitlines()
            if line.startswith("-") and not line.startswith("---")
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
