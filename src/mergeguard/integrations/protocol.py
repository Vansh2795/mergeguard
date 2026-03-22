"""Platform-agnostic SCM client protocol.

Defines the interface that both GitHubClient and GitLabClient implement,
enabling dependency injection in the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mergeguard.models import ChangedFile, PRInfo


class SCMError(Exception):
    """Base exception for SCM client API errors."""


@dataclass
class ReviewComment:
    """A single inline comment on a PR diff."""

    path: str
    line: int  # Line number in the new file
    body: str
    side: str = field(default="RIGHT")  # RIGHT = new file, LEFT = old file


@runtime_checkable
class SCMClient(Protocol):
    """Protocol for source-code management platform clients."""

    def get_open_prs(
        self, max_count: int = 200, max_age_days: int | None = None
    ) -> list[PRInfo]: ...

    def get_pr(self, number: int) -> PRInfo: ...

    def get_pr_files(self, pr_number: int) -> list[ChangedFile]: ...

    def get_pr_diff(self, pr_number: int) -> str: ...

    def get_file_content(self, path: str, ref: str) -> str | None: ...

    def post_pr_comment(self, pr_number: int, body: str) -> None: ...

    def post_pr_review(
        self,
        pr_number: int,
        body: str,
        comments: list[ReviewComment],
        event: str = "COMMENT",
    ) -> None: ...

    def post_commit_status(
        self,
        sha: str,
        state: str,
        description: str,
        target_url: str = "",
        context: str = "mergeguard/cross-pr-analysis",
    ) -> None: ...
