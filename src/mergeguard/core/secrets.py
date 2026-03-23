"""Secret scanning for PR diffs.

Detects accidentally committed secrets (API keys, tokens, private keys)
in added lines of PR diffs using regex pattern matching.
"""

from __future__ import annotations

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

    # Pre-compile allowlist patterns
    compiled_allowlist: list[re.Pattern[str]] = []
    for al in config.secrets.allowlist:
        try:
            compiled_allowlist.append(re.compile(al))
        except re.error:
            logger.warning("Invalid allowlist regex: %s", al)

    conflicts: list[Conflict] = []
    seen: set[tuple[str, int, str]] = set()  # (file, line, pattern_name)

    for cf in pr.changed_files:
        if not cf.patch:
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
                    if any(al.search(content) for al in compiled_allowlist):
                        continue

                    for pattern, regex in compiled:
                        match = regex.search(content)
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
