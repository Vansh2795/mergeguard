"""Optional LLM-powered semantic conflict analysis."""

from __future__ import annotations

import json
import logging
import os

from mergeguard.models import Conflict, ConflictSeverity, ConflictType

logger = logging.getLogger(__name__)

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

FIX_SUGGESTION_PROMPT = """You are a senior engineer helping resolve a cross-PR conflict.
Generate a specific, actionable fix suggestion for the current PR author.

Conflict type: {conflict_type}
Severity: {severity}
File: {file_path}
{symbol_line}
Source PR: #{source_pr}
Conflicting PR: #{target_pr}

Source PR diff:
```
{source_diff}
```

Conflicting PR diff:
```
{target_diff}
```

Based on the conflict type, provide a concrete suggestion:
- Hard conflict: Tell them to rebase and resolve the overlap, specifying which lines/function
- Interface conflict: Identify the signature change and tell them exactly what to update
- Behavioral conflict: Explain how both changes interact and suggest coordination
- Duplication: Point out the overlap and suggest reusing the other PR's implementation

Respond with ONLY the fix suggestion text (1-3 sentences). Be specific about file names, \
function names, and line numbers. Do not include any JSON or markdown formatting."""


BATCH_FIX_SUGGESTION_PROMPT = """You are a senior engineer helping resolve cross-PR conflicts.
Generate specific, actionable fix suggestions for the current PR author.

File: {file_path}
Source PR: #{source_pr}
Conflicting PR: #{target_pr}

Source PR diff:
```
{source_diff}
```

Conflicting PR diff:
```
{target_diff}
```

There are {count} conflicts in this file:
{conflict_list}

For each conflict, provide a concrete suggestion (1-3 sentences). Be specific about
function names and line numbers. Respond in JSON format:
[{{"index": 0, "suggestion": "..."}}, {{"index": 1, "suggestion": "..."}}]

Respond with ONLY the JSON array. No markdown formatting."""

_DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
}


def _resolve_provider(provider: str) -> str | None:
    """Resolve 'auto' provider to a concrete provider based on available API keys."""
    if provider == "openai":
        return "openai"
    if provider == "anthropic":
        return "anthropic"
    # auto-detect
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


class LLMAnalyzer:
    """Uses LLMs to assess semantic compatibility of code changes.

    Supports both OpenAI and Anthropic as providers.
    """

    def __init__(
        self,
        model: str | None = None,
        provider: str = "auto",
        api_key: str | None = None,
    ):
        self._provider = _resolve_provider(provider)
        if self._provider is None:
            raise ValueError(
                "No LLM provider available. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
            )

        if self._provider == "openai":
            self._init_openai(api_key or os.environ.get("OPENAI_API_KEY", ""), model)
        else:
            self._init_anthropic(api_key or os.environ.get("ANTHROPIC_API_KEY", ""), model)

    def _init_openai(self, api_key: str, model: str | None) -> None:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenAI LLM analysis. "
                "Install it with: pip install 'mergeguard[llm-openai]'"
            ) from None
        self._openai_client = OpenAI(api_key=api_key)
        self._model = model or _DEFAULT_MODELS["openai"]

    def _init_anthropic(self, api_key: str, model: str | None) -> None:
        try:
            from anthropic import Anthropic  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for Anthropic LLM analysis. "
                "Install it with: pip install 'mergeguard[llm-anthropic]'"
            ) from None
        self._anthropic_client = Anthropic(api_key=api_key)
        self._model = model or _DEFAULT_MODELS["anthropic"]

    def _llm_call(self, prompt: str, max_tokens: int = 500) -> str:
        """Dispatch a prompt to the configured LLM provider and return the text response."""
        if self._provider == "openai":
            response = self._openai_client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""
        else:
            response = self._anthropic_client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

    def analyze_behavioral_conflict(
        self,
        symbol_name: str,
        file_path: str,
        pr_a_number: int,
        pr_a_diff: str,
        pr_b_number: int,
        pr_b_diff: str,
    ) -> Conflict | None:
        """Ask the LLM whether two changes to the same function are compatible."""
        prompt = CONFLICT_ANALYSIS_PROMPT.format(
            symbol_name=symbol_name,
            file_path=file_path,
            pr_a_number=pr_a_number,
            pr_a_diff=pr_a_diff[:2000],
            pr_b_number=pr_b_number,
            pr_b_diff=pr_b_diff[:2000],
        )

        raw = self._llm_call(prompt, max_tokens=500)

        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return None

        if not isinstance(result, dict):
            return None

        if result.get("compatible", True):
            return None

        severity_map = {
            "critical": ConflictSeverity.CRITICAL,
            "warning": ConflictSeverity.WARNING,
            "info": ConflictSeverity.INFO,
        }

        return Conflict(
            conflict_type=ConflictType.BEHAVIORAL,
            severity=severity_map.get(result.get("severity", "warning"), ConflictSeverity.WARNING),
            source_pr=pr_a_number,
            target_pr=pr_b_number,
            file_path=file_path,
            symbol_name=symbol_name,
            description=result.get(
                "explanation", "Potential behavioral conflict detected by AI analysis."
            ),
            recommendation=result.get("recommendation", "Review both changes before merging."),
        )

    def generate_fix_suggestion(
        self,
        conflict: Conflict,
        source_diff: str,
        target_diff: str,
    ) -> str | None:
        """Generate a specific, actionable fix suggestion for a conflict."""
        symbol_line = (
            f"Symbol: {conflict.symbol_name}" if conflict.symbol_name else "File-level conflict"
        )
        prompt = FIX_SUGGESTION_PROMPT.format(
            conflict_type=conflict.conflict_type.value,
            severity=conflict.severity.value,
            file_path=conflict.file_path,
            symbol_line=symbol_line,
            source_pr=conflict.source_pr,
            target_pr=conflict.target_pr,
            source_diff=source_diff[:2000],
            target_diff=target_diff[:2000],
        )

        try:
            result = self._llm_call(prompt, max_tokens=300)
            return result.strip() or None
        except Exception:
            logger.debug("Fix suggestion generation failed", exc_info=True)
            return None

    def generate_fix_suggestions_batch(
        self,
        conflicts: list[Conflict],
        source_diff: str,
        target_diff: str,
    ) -> list[str | None]:
        """Generate fix suggestions for multiple conflicts in one LLM call.

        All conflicts should share the same file_path and target_pr so diffs
        can be reused. Returns a list of suggestions aligned with the input list.
        """
        conflict_lines = []
        for i, c in enumerate(conflicts):
            symbol_info = f" (symbol: `{c.symbol_name}`)" if c.symbol_name else ""
            conflict_lines.append(
                f"  {i}. [{c.conflict_type.value}] [{c.severity.value}]{symbol_info}: "
                f"{c.description}"
            )

        prompt = BATCH_FIX_SUGGESTION_PROMPT.format(
            file_path=conflicts[0].file_path,
            source_pr=conflicts[0].source_pr,
            target_pr=conflicts[0].target_pr,
            source_diff=source_diff[:2000],
            target_diff=target_diff[:2000],
            count=len(conflicts),
            conflict_list="\n".join(conflict_lines),
        )

        max_tokens = min(300 * len(conflicts), 2000)
        try:
            raw = self._llm_call(prompt, max_tokens=max_tokens)
            results = json.loads(raw)
        except (json.JSONDecodeError, Exception):
            logger.debug("Batch fix suggestion generation failed", exc_info=True)
            return [None] * len(conflicts)

        if not isinstance(results, list):
            return [None] * len(conflicts)

        # Map index→suggestion
        suggestion_map: dict[int, str] = {}
        for item in results:
            if isinstance(item, dict) and "index" in item and "suggestion" in item:
                idx = item["index"]
                text = str(item["suggestion"]).strip()
                if text:
                    suggestion_map[idx] = text

        return [suggestion_map.get(i) for i in range(len(conflicts))]
