"""SARIF v2.1.0 output formatter for MergeGuard analyze reports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mergeguard.models import ConflictReport

from mergeguard.models import ConflictSeverity, ConflictType

SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json"

RULE_IDS: dict[ConflictType, str] = {
    ConflictType.HARD: "mergeguard/hard-conflict",
    ConflictType.INTERFACE: "mergeguard/interface-conflict",
    ConflictType.BEHAVIORAL: "mergeguard/behavioral-conflict",
    ConflictType.DUPLICATION: "mergeguard/duplication",
    ConflictType.TRANSITIVE: "mergeguard/transitive-conflict",
    ConflictType.REGRESSION: "mergeguard/regression",
    ConflictType.GUARDRAIL: "mergeguard/guardrail-violation",
    ConflictType.SECRET: "mergeguard/secret-detected",
}

_SEVERITY_MAP: dict[ConflictSeverity, str] = {
    ConflictSeverity.CRITICAL: "error",
    ConflictSeverity.WARNING: "warning",
    ConflictSeverity.INFO: "note",
}


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("py-mergeguard")
    except Exception:
        return "0.0.0"


def format_sarif(report: ConflictReport) -> str:
    """Format a ConflictReport as SARIF v2.1.0 JSON."""
    results: list[dict[str, Any]] = []
    used_rule_ids: set[str] = set()

    for conflict in report.conflicts:
        rule_id = RULE_IDS[conflict.conflict_type]
        used_rule_ids.add(rule_id)

        location: dict[str, Any] = {
            "physicalLocation": {
                "artifactLocation": {"uri": conflict.file_path},
            }
        }
        if conflict.source_lines is not None:
            location["physicalLocation"]["region"] = {
                "startLine": conflict.source_lines[0],
                "endLine": conflict.source_lines[1],
            }

        message_text = f"{conflict.description} (conflicts with PR #{conflict.target_pr})"
        if conflict.fix_suggestion is not None:
            message_text += f"\n\nSuggested Fix: {conflict.fix_suggestion}"

        results.append(
            {
                "ruleId": rule_id,
                "level": _SEVERITY_MAP[conflict.severity],
                "message": {
                    "text": message_text,
                },
                "locations": [location],
            }
        )

    # Only include rules that actually appear in results
    rules = [
        {"id": rule_id, "shortDescription": {"text": rule_id}}
        for rule_id in RULE_IDS.values()
        if rule_id in used_rule_ids
    ]

    sarif: dict[str, Any] = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "MergeGuard",
                        "version": _get_version(),
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }

    return json.dumps(sarif, indent=2)
