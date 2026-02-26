"""Main orchestrator — ties everything together.

The MergeGuardEngine is the top-level entry point that coordinates
all analysis steps: fetching PRs, parsing diffs, detecting conflicts,
computing risk scores, and generating reports.
"""

from __future__ import annotations

import time

from mergeguard.analysis.attribution import detect_attribution
from mergeguard.analysis.diff_parser import parse_unified_diff
from mergeguard.analysis.symbol_index import SymbolIndex
from mergeguard.core.conflict import classify_conflicts, compute_file_overlaps
from mergeguard.core.risk_scorer import compute_risk_score
from mergeguard.integrations.github_client import GitHubClient
from mergeguard.models import (
    ChangedSymbol,
    ConflictReport,
    MergeGuardConfig,
    PRInfo,
)


class MergeGuardEngine:
    """Top-level engine that orchestrates the full analysis pipeline."""

    def __init__(
        self,
        token: str,
        repo_full_name: str,
        config: MergeGuardConfig,
    ):
        self._client = GitHubClient(token, repo_full_name)
        self._config = config
        self._repo_full_name = repo_full_name
        self._symbol_index = SymbolIndex()

    def analyze_pr(self, pr_number: int) -> ConflictReport:
        """Analyze a single PR for cross-PR conflicts.

        This is the main entry point for analyzing a PR:
        1. Fetch the target PR and all other open PRs
        2. Parse diffs and extract changed symbols
        3. Detect conflicts between the target PR and all other PRs
        4. Compute risk score
        5. Return the conflict report
        """
        start_time = time.monotonic()

        # Step 1: Fetch PRs
        target_pr = self._client.get_pr(pr_number)
        target_pr.changed_files = self._client.get_pr_files(pr_number)
        other_prs = self._client.get_open_prs(max_count=self._config.max_open_prs)

        # Step 2: Enrich with diff data and symbols
        self._enrich_pr(target_pr)
        for other_pr in other_prs:
            if other_pr.number == pr_number:
                continue
            other_pr.changed_files = self._client.get_pr_files(other_pr.number)
            self._enrich_pr(other_pr)

        # Step 3: Detect AI attribution
        target_pr.ai_attribution = detect_attribution(target_pr)

        # Step 4: Detect conflicts
        all_conflicts = []
        no_conflict_prs = []
        file_overlaps = compute_file_overlaps(target_pr, other_prs)

        for other_pr in other_prs:
            if other_pr.number == pr_number:
                continue
            overlaps = file_overlaps.get(other_pr.number, [])
            if not overlaps:
                no_conflict_prs.append(other_pr.number)
                continue

            conflicts = classify_conflicts(target_pr, other_pr, overlaps)
            all_conflicts.extend(conflicts)
            if not conflicts:
                no_conflict_prs.append(other_pr.number)

        # Step 5: Compute risk score
        risk_score, risk_factors = compute_risk_score(
            pr=target_pr,
            conflicts=all_conflicts,
            dependency_depth=0,  # TODO: compute from dependency graph
            churn_score=0.0,  # TODO: compute from git history
            pattern_deviation_score=0.0,  # TODO: compute from AST comparison
            config=self._config,
        )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        return ConflictReport(
            pr=target_pr,
            conflicts=all_conflicts,
            risk_score=risk_score,
            risk_factors=risk_factors,
            no_conflict_prs=no_conflict_prs,
            analysis_duration_ms=elapsed_ms,
        )

    def analyze_all_open_prs(self) -> list[ConflictReport]:
        """Analyze all open PRs and return a list of reports.

        Used by the dashboard command to show risk scores for all PRs.
        """
        prs = self._client.get_open_prs(max_count=self._config.max_open_prs)
        reports = []
        for pr in prs:
            report = self.analyze_pr(pr.number)
            reports.append(report)
        return reports

    def _enrich_pr(self, pr: PRInfo) -> None:
        """Enrich a PR with diff data and changed symbols."""
        for changed_file in pr.changed_files:
            if not changed_file.patch:
                continue

            # Parse the diff to get modified line ranges
            diff_text = f"diff --git a/{changed_file.path} b/{changed_file.path}\n"
            diff_text += f"--- a/{changed_file.path}\n"
            diff_text += f"+++ b/{changed_file.path}\n"
            diff_text += changed_file.patch
            file_diffs = parse_unified_diff(diff_text)

            if not file_diffs:
                continue

            modified_ranges = file_diffs[0].all_modified_line_ranges
            if not modified_ranges:
                continue

            # Fetch file content and extract symbols
            content = self._client.get_file_content(
                changed_file.path, pr.base_branch
            )
            if not content:
                continue

            symbols = self._symbol_index.get_symbols(
                changed_file.path, content, pr.base_branch
            )

            # Map modified ranges to symbols
            from mergeguard.analysis.ast_parser import map_diff_to_symbols

            affected = map_diff_to_symbols(symbols, modified_ranges)
            for symbol in affected:
                pr.changed_symbols.append(
                    ChangedSymbol(
                        symbol=symbol,
                        change_type="modified_body",
                        diff_lines=modified_ranges[0] if modified_ranges else (0, 0),
                    )
                )
