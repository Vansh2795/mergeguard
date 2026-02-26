"""Optional LLM-powered semantic conflict analysis."""

from __future__ import annotations

import json

from mergeguard.models import Conflict, ConflictSeverity, ConflictType

CONFLICT_ANALYSIS_PROMPT = """You are analyzing two code changes from different pull requests
that modify the same function. Determine if these changes are semantically compatible.

Function: {symbol_name}
File: {file_path}

PR #{pr_a_number} changes:
```
{pr_a_diff}
```

PR #{pr_b_number} changes:
```
{pr_b_diff}
```

Analyze these changes and respond in JSON format:
{{
  "compatible": true/false,
  "severity": "critical" | "warning" | "info",
  "explanation": "Brief explanation of why these changes do or don't conflict",
  "recommendation": "What the developer should do"
}}

Rules:
- "critical": Changes are fundamentally incompatible; merging both will break the code
- "warning": Changes might interact unexpectedly; human review recommended
- "info": Changes overlap in the same file/function but are likely independent
"""


class LLMAnalyzer:
    """Uses Claude to assess semantic compatibility of code changes."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for LLM analysis. "
                "Install it with: pip install 'mergeguard[llm]'"
            )
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def analyze_behavioral_conflict(
        self,
        symbol_name: str,
        file_path: str,
        pr_a_number: int,
        pr_a_diff: str,
        pr_b_number: int,
        pr_b_diff: str,
    ) -> Conflict | None:
        """Ask Claude whether two changes to the same function are compatible."""
        prompt = CONFLICT_ANALYSIS_PROMPT.format(
            symbol_name=symbol_name,
            file_path=file_path,
            pr_a_number=pr_a_number,
            pr_a_diff=pr_a_diff[:2000],  # Limit to manage token costs
            pr_b_number=pr_b_number,
            pr_b_diff=pr_b_diff[:2000],
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            result = json.loads(response.content[0].text)
        except (json.JSONDecodeError, IndexError):
            return None

        if result.get("compatible", True):
            return None  # No conflict

        severity_map = {
            "critical": ConflictSeverity.CRITICAL,
            "warning": ConflictSeverity.WARNING,
            "info": ConflictSeverity.INFO,
        }

        return Conflict(
            conflict_type=ConflictType.BEHAVIORAL,
            severity=severity_map.get(
                result.get("severity", "warning"), ConflictSeverity.WARNING
            ),
            source_pr=pr_a_number,
            target_pr=pr_b_number,
            file_path=file_path,
            symbol_name=symbol_name,
            description=result.get(
                "explanation", "Potential behavioral conflict detected by AI analysis."
            ),
            recommendation=result.get(
                "recommendation", "Review both changes before merging."
            ),
        )
