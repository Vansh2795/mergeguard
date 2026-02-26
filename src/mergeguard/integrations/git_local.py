"""Local git operations for CLI mode.

Provides git operations using subprocess calls for when
MergeGuard is run locally against a git repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitLocalClient:
    """Execute git operations on a local repository."""

    def __init__(self, repo_path: str | Path = "."):
        self._repo_path = Path(repo_path).resolve()
        if not (self._repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {self._repo_path}")

    def get_current_branch(self) -> str:
        """Get the name of the current branch."""
        result = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return result.strip()

    def get_remote_url(self) -> str | None:
        """Get the remote origin URL."""
        try:
            result = self._run(["git", "remote", "get-url", "origin"])
            return result.strip()
        except subprocess.CalledProcessError:
            return None

    def get_repo_full_name(self) -> str | None:
        """Extract owner/repo from the remote URL."""
        url = self.get_remote_url()
        if not url:
            return None

        # Handle SSH URLs: git@github.com:owner/repo.git
        if url.startswith("git@"):
            parts = url.split(":")[-1]
            return parts.removesuffix(".git")

        # Handle HTTPS URLs: https://github.com/owner/repo.git
        if "github.com" in url:
            parts = url.split("github.com/")[-1]
            return parts.removesuffix(".git")

        return None

    def get_diff(self, base: str, head: str = "HEAD") -> str:
        """Get the unified diff between two refs."""
        return self._run(["git", "diff", f"{base}...{head}"])

    def get_file_content(self, path: str, ref: str = "HEAD") -> str | None:
        """Get file content at a specific ref."""
        try:
            return self._run(["git", "show", f"{ref}:{path}"])
        except subprocess.CalledProcessError:
            return None

    def get_changed_files(self, base: str, head: str = "HEAD") -> list[str]:
        """Get list of files changed between two refs."""
        result = self._run(["git", "diff", "--name-only", f"{base}...{head}"])
        return [f for f in result.strip().split("\n") if f]

    def get_merge_base(self, branch_a: str, branch_b: str) -> str:
        """Find the merge base (common ancestor) of two branches."""
        result = self._run(["git", "merge-base", branch_a, branch_b])
        return result.strip()

    def _run(self, cmd: list[str]) -> str:
        """Run a git command and return stdout."""
        result = subprocess.run(
            cmd,
            cwd=self._repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
