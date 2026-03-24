"""Secret scanning for PR diffs.

Detects accidentally committed secrets (API keys, tokens, private keys)
in added lines of PR diffs using regex pattern matching.
"""

from __future__ import annotations

import fnmatch
import logging
import re

from mergeguard.analysis.diff_parser import parse_unified_diff
from mergeguard.models import (
    Conflict,
    ConflictType,
    MergeGuardConfig,
    PRInfo,
    SecretPattern,
)

logger = logging.getLogger(__name__)

_MAX_LINE_LENGTH = 10_000


def _safe_search(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """Search with line-length cap to mitigate ReDoS on user-supplied patterns."""
    if len(text) > _MAX_LINE_LENGTH:
        text = text[:_MAX_LINE_LENGTH]
    return pattern.search(text)


BUILTIN_ALLOWLIST: list[str] = [
    r"EXAMPLE",  # AWS's documented example key suffix
    r"(?i)placeholder",
    r"(?i)your[_\-]?(api[_\-]?key|secret|token|password)",
    r"(?i)(fake|dummy|test|mock)[_\-]?(key|secret|token|password)",
    r"<[A-Z_]+>",  # Template placeholders like <API_KEY>
]


def _redact(value: str) -> str:
    """Redact a secret value, showing only first 4 and last 3 chars."""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-3:]}"


def scan_secrets(pr: PRInfo, config: MergeGuardConfig) -> list[Conflict]:
    """Scan PR diff for accidentally committed secrets.

    Args:
        pr: The PR to scan.
        config: Configuration with secrets settings.

    Returns:
        List of secret findings as Conflict objects.
    """
    if not config.secrets.enabled:
        return []

    # Merge builtin + custom patterns
    patterns: list[SecretPattern] = []
    if config.secrets.use_builtin_patterns:
        from mergeguard.core.secret_patterns import BUILTIN_PATTERNS

        patterns.extend(BUILTIN_PATTERNS)
    patterns.extend(config.secrets.patterns)

    if not patterns:
        return []

    # Pre-compile all regexes
    compiled: list[tuple[SecretPattern, re.Pattern[str]]] = []
    for p in patterns:
        try:
            compiled.append((p, re.compile(p.pattern)))
        except re.error:
            logger.warning("Invalid secret pattern regex for '%s': %s", p.name, p.pattern)

    # Pre-compile allowlist patterns (builtin + user-defined)
    compiled_allowlist: list[re.Pattern[str]] = []
    for al in BUILTIN_ALLOWLIST + config.secrets.allowlist:
        try:
            compiled_allowlist.append(re.compile(al))
        except re.error:
            logger.warning("Invalid allowlist regex: %s", al)

    # Path patterns to skip (test files, fixtures, etc.)
    ignored = config.secrets.ignored_paths

    conflicts: list[Conflict] = []
    seen: set[tuple[str, int, str]] = set()  # (file, line, pattern_name)

    for cf in pr.changed_files:
        if not cf.patch:
            continue

        if any(fnmatch.fnmatch(cf.path, pat) for pat in ignored):
            continue

        # Construct full diff text for the parser
        diff_text = (
            f"diff --git a/{cf.path} b/{cf.path}\n--- a/{cf.path}\n+++ b/{cf.path}\n{cf.patch}"
        )
        file_diffs = parse_unified_diff(diff_text)
        if not file_diffs:
            continue

        for fd in file_diffs:
            for hunk in fd.hunks:
                for line_num, content in hunk.added_lines:
                    # Check allowlist first
                    if any(_safe_search(al, content) for al in compiled_allowlist):
                        continue

                    for pattern, regex in compiled:
                        match = _safe_search(regex, content)
                        if not match:
                            continue

                        key = (cf.path, line_num, pattern.name)
                        if key in seen:
                            continue
                        seen.add(key)

                        redacted = _redact(match.group(0))
                        conflicts.append(
                            Conflict(
                                conflict_type=ConflictType.SECRET,
                                severity=pattern.severity,
                                source_pr=pr.number,
                                target_pr=pr.number,
                                file_path=cf.path,
                                source_lines=(line_num, line_num),
                                symbol_name=pattern.name,
                                description=(
                                    f"Potential {pattern.name} detected: `{redacted}` "
                                    f"in `{cf.path}` at line {line_num}."
                                ),
                                recommendation="Remove the secret and rotate it immediately.",
                            )
                        )

    return conflicts
