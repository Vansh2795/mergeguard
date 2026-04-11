"""File-based SCM client for offline benchmarks.

Reads PR data and file contents from pre-captured JSON fixtures,
implementing the SCMClient protocol with zero API calls.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mergeguard.integrations.protocol import ReviewComment
from mergeguard.models import ChangedFile, FileChangeStatus, PRInfo


class FileBasedSCMClient:
    """SCM client backed by captured fixture data. Zero network calls."""

    def __init__(self, fixture_data: dict[str, Any]) -> None:
        self._repo = fixture_data.get("repo", "unknown/repo")
        self._file_contents: dict[str, str] = fixture_data.get("file_contents", {})

        # Parse PRs and their changed files
        self._prs: list[PRInfo] = []
        self._pr_files: dict[int, list[ChangedFile]] = {}

        for pr_data in fixture_data.get("prs", []):
            changed_files_raw = pr_data.pop("changed_files", [])
            # Parse dates if they're strings
            for date_field in ("created_at", "updated_at"):
                val = pr_data.get(date_field)
                if isinstance(val, str):
                    pr_data[date_field] = datetime.fromisoformat(val)

            pr = PRInfo(**pr_data)
            self._prs.append(pr)

            files = []
            for cf_data in changed_files_raw:
                if isinstance(cf_data.get("status"), str):
                    cf_data["status"] = FileChangeStatus(cf_data["status"])
                files.append(ChangedFile(**cf_data))
            self._pr_files[pr.number] = files

    def close(self) -> None:
        pass

    def get_open_prs(
        self, max_count: int = 200, max_age_days: int | None = None
    ) -> list[PRInfo]:
        return self._prs[:max_count]

    def get_pr(self, number: int) -> PRInfo:
        for pr in self._prs:
            if pr.number == number:
                return pr
        raise ValueError(f"PR #{number} not found in fixture")

    def get_pr_files(self, pr_number: int) -> list[ChangedFile]:
        return self._pr_files.get(pr_number, [])

    def get_pr_diff(self, pr_number: int) -> str:
        files = self._pr_files.get(pr_number, [])
        parts = []
        for f in files:
            if f.patch:
                parts.append(f"diff --git a/{f.path} b/{f.path}")
                parts.append(f"--- a/{f.path}")
                parts.append(f"+++ b/{f.path}")
                parts.append(f.patch)
        return "\n".join(parts)

    def get_file_content(self, path: str, ref: str) -> str | None:
        return self._file_contents.get(f"{ref}:{path}")

    def post_pr_comment(self, pr_number: int, body: str) -> None:
        pass

    def post_pr_review(
        self,
        pr_number: int,
        body: str,
        comments: list[ReviewComment] | None = None,
        event: str = "COMMENT",
    ) -> None:
        pass

    def post_commit_status(
        self,
        sha: str,
        state: str,
        description: str,
        target_url: str = "",
        context: str = "mergeguard/cross-pr-analysis",
    ) -> None:
        pass

    def add_labels(self, pr_number: int, labels: list[str]) -> None:
        pass

    def request_reviewers(self, pr_number: int, reviewers: list[str]) -> None:
        pass

    @property
    def rate_limit_remaining(self) -> int:
        return 5000
