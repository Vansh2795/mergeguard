"""CODEOWNERS parser supporting GitHub and GitLab formats.

Parses CODEOWNERS files to resolve file → owner mappings, enabling
team-aware conflict routing and @mention tagging in PR comments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mergeguard.integrations.protocol import SCMClient

logger = logging.getLogger(__name__)

# Standard CODEOWNERS file locations, checked in order
_CODEOWNERS_PATHS = (
    ".github/CODEOWNERS",
    "CODEOWNERS",
    "docs/CODEOWNERS",
)


@dataclass
class CodeOwnerRule:
    """A single CODEOWNERS pattern → owners mapping."""

    pattern: str
    owners: list[str]
    section: str | None = None  # GitLab section header, e.g. "[Frontend]"


@dataclass
class CodeOwners:
    """Parsed CODEOWNERS file with pattern matching.

    Supports both GitHub format (flat, last-match-wins) and
    GitLab format (with ``[Section]`` headers for scoped ownership).
    """

    rules: list[CodeOwnerRule] = field(default_factory=list)

    def __init__(self, content: str, *, gitlab: bool = False) -> None:
        if gitlab:
            self.rules = self._parse_gitlab(content.splitlines())
        else:
            self.rules = self._parse_github(content.splitlines())

    @staticmethod
    def _parse_github(lines: list[str]) -> list[CodeOwnerRule]:
        """Parse GitHub CODEOWNERS format.

        Each non-comment, non-empty line is: ``PATTERN @owner1 @owner2 ...``
        Last matching rule wins (standard GitHub behavior).
        """
        rules: list[CodeOwnerRule] = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pattern = parts[0]
            owners = [p for p in parts[1:] if not p.startswith("#")]
            rules.append(CodeOwnerRule(pattern=pattern, owners=owners))
        return rules

    @staticmethod
    def _parse_gitlab(lines: list[str]) -> list[CodeOwnerRule]:
        """Parse GitLab CODEOWNERS format with ``[Section]`` headers.

        Section headers like ``[Frontend]`` scope subsequent rules.
        Lines outside any section are treated as global (section=None).
        """
        rules: list[CodeOwnerRule] = []
        current_section: str | None = None
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Section header: [SectionName] or ^[SectionName]
            if line.startswith("[") or line.startswith("^["):
                bracket_start = line.index("[")
                bracket_end = line.index("]", bracket_start)
                current_section = line[bracket_start + 1 : bracket_end]
                # Optional default owners after the section header
                remainder = line[bracket_end + 1 :].strip()
                if remainder:
                    section_owners = [p for p in remainder.split() if not p.startswith("#")]
                    if section_owners:
                        rules.append(
                            CodeOwnerRule(
                                pattern="*",
                                owners=section_owners,
                                section=current_section,
                            )
                        )
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pattern = parts[0]
            owners = [p for p in parts[1:] if not p.startswith("#")]
            rules.append(CodeOwnerRule(pattern=pattern, owners=owners, section=current_section))
        return rules

    def resolve_owners(self, file_path: str) -> list[str]:
        """Resolve owners for a single file path (last-match-wins)."""
        matched_owners: list[str] = []
        for rule in self.rules:
            if _pattern_matches(rule.pattern, file_path):
                matched_owners = rule.owners
        return matched_owners

    def resolve_owners_for_files(self, file_paths: Iterable[str]) -> dict[str, list[str]]:
        """Batch resolve owners for multiple file paths."""
        return {fp: self.resolve_owners(fp) for fp in file_paths}


def _pattern_matches(pattern: str, file_path: str) -> bool:
    """Match a CODEOWNERS glob pattern against a file path.

    CODEOWNERS patterns follow these rules:
    - ``*`` matches everything (default owner)
    - ``*.py`` matches any .py file at any depth
    - ``/docs/`` matches the docs directory at root
    - ``docs/`` matches docs directory anywhere
    - ``src/utils/*`` matches files directly in src/utils/
    - ``src/**`` matches everything under src/
    """
    import fnmatch as _fnmatch

    # Normalize: strip leading slash (CODEOWNERS treats /pattern as root-anchored)
    anchored = pattern.startswith("/")
    p = pattern.lstrip("/")

    # Trailing slash means "directory and everything inside"
    if p.endswith("/"):
        p = p + "**"

    # Replace ** with a multi-segment match: fnmatch's * doesn't cross /,
    # so we convert ** patterns to a regex-friendly form via fnmatch on
    # each segment after splitting.
    if "**" in p:
        # Convert ** to match any number of path segments
        # e.g., "src/**/*.py" -> regex that matches src/a/b/c/foo.py
        # fnmatch.translate turns * into [^/]* but ** needs to match /
        # Replace ** with a sentinel, translate, then fix the sentinel
        import re

        sentinel = "__DOUBLE_STAR__"
        p_sentinel = p.replace("**", sentinel)
        regex = _fnmatch.translate(p_sentinel)
        # fnmatch.translate wraps in (?s:...) and $ — replace sentinel match
        regex = regex.replace(sentinel, ".*")
        return bool(re.fullmatch(regex, file_path))

    # If pattern has no slash, it can match at any depth
    if "/" not in p:
        return _fnmatch.fnmatch(file_path, p) or _fnmatch.fnmatch(file_path.rsplit("/", 1)[-1], p)

    # Pattern has a slash — match against full path
    if anchored:
        return _fnmatch.fnmatch(file_path, p)

    # Non-anchored pattern with slash: try both root-relative and any-depth
    if _fnmatch.fnmatch(file_path, p):
        return True
    return _fnmatch.fnmatch(file_path, "**/" + p)


def load_codeowners(client: SCMClient, repo: str, ref: str = "HEAD") -> CodeOwners | None:
    """Load and parse CODEOWNERS from the repository.

    Tries standard locations in order: .github/CODEOWNERS, CODEOWNERS, docs/CODEOWNERS.
    Returns None if no CODEOWNERS file is found.
    """
    for path in _CODEOWNERS_PATHS:
        try:
            content = client.get_file_content(path, ref)
            if content is not None:
                # GitLab format detected by presence of section headers
                is_gitlab = any(
                    line.strip().startswith("[") or line.strip().startswith("^[")
                    for line in content.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                )
                logger.info("Loaded CODEOWNERS from %s (gitlab=%s)", path, is_gitlab)
                return CodeOwners(content, gitlab=is_gitlab)
        except Exception:
            logger.debug("Failed to fetch %s", path, exc_info=True)
            continue

    logger.debug("No CODEOWNERS file found in %s", repo)
    return None
