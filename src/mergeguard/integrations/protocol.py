"""Platform-agnostic SCM client protocol.

Defines the interface that both GitHubClient and GitLabClient implement,
enabling dependency injection in the engine.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mergeguard.models import ChangedFile, PRInfo


class SCMError(Exception):
    """Base exception for SCM client API errors."""


@runtime_checkable
class SCMClient(Protocol):
    """Protocol for source-code management platform clients."""

    def get_open_prs(self, max_count: int = 200, max_age_days: int | None = None) -> list[PRInfo]: ...

    def get_pr(self, number: int) -> PRInfo: ...

    def get_pr_files(self, pr_number: int) -> list[ChangedFile]: ...

    def get_pr_diff(self, pr_number: int) -> str: ...

    def get_file_content(self, path: str, ref: str) -> str | None: ...

    def post_pr_comment(self, pr_number: int, body: str) -> None: ...
