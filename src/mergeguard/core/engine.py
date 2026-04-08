"""Main orchestrator — ties everything together.

The MergeGuardEngine is the top-level entry point that coordinates
all analysis steps: fetching PRs, parsing diffs, detecting conflicts,
computing risk scores, and generating reports.
"""

from __future__ import annotations

import fnmatch
import logging
import re as _re
import sqlite3
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mergeguard.integrations.llm_analyzer import LLMAnalyzer

import httpx

from mergeguard.analysis.ast_parser import map_diff_to_symbols  # used in fork fallback
from mergeguard.analysis.attribution import detect_attribution
from mergeguard.analysis.codeowners import CodeOwners, load_codeowners
from mergeguard.analysis.dependency import DependencyGraph, build_dependency_graph
from mergeguard.analysis.diff_parser import FileDiff, parse_unified_diff
from mergeguard.analysis.similarity import symbol_name_similarity
from mergeguard.analysis.stacked_prs import build_stack_lookup, detect_stacks
from mergeguard.analysis.symbol_index import SymbolIndex
from mergeguard.core.conflict import classify_conflicts, compute_file_overlaps
from mergeguard.core.guardrails import enforce_guardrails
from mergeguard.core.regression import detect_regressions
from mergeguard.core.risk_scorer import compute_risk_score
from mergeguard.integrations.github_client import GitHubClient
from mergeguard.integrations.protocol import SCMClient, SCMError
from mergeguard.models import (
    ChangedFile,
    ChangedSymbol,
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    FileChangeStatus,
    MergeGuardConfig,
    PRInfo,
    StackGroup,
    Symbol,
    SymbolType,
)
from mergeguard.storage.cache import AnalysisCache
from mergeguard.storage.decisions_log import DecisionsLog

logger = logging.getLogger(__name__)


def _demote_intra_stack_conflicts(
    conflicts: list[Conflict],
    stack_lookup: dict[int, StackGroup],
) -> None:
    """Demote conflicts between PRs in the same stack to INFO severity.

    Modifies conflicts in-place: sets is_intra_stack, preserves original_severity,
    and downgrades severity to INFO.
    """
    for conflict in conflicts:
        src_group = stack_lookup.get(conflict.source_pr)
        tgt_group = stack_lookup.get(conflict.target_pr)
        if (
            src_group is not None
            and tgt_group is not None
            and src_group.group_id == tgt_group.group_id
        ):
            conflict.is_intra_stack = True
            conflict.original_severity = conflict.severity
            conflict.severity = ConflictSeverity.INFO


def _extract_symbol_diff(file_diff: FileDiff, symbol: Symbol) -> str | None:
    """Extract diff lines that fall within a symbol's line range."""
    lines: list[str] = []
    for hunk in file_diff.hunks:
        for ln, content in hunk.added_lines:
            if symbol.start_line <= ln <= symbol.end_line:
                lines.append(f"+{content}")
        for ln, content in hunk.removed_lines:
            if symbol.start_line <= ln <= symbol.end_line:
                lines.append(f"-{content}")
    return "\n".join(lines) if lines else None


def _extract_symbol_diff_head(file_diff: FileDiff, symbol: Symbol) -> str | None:
    """Extract diff lines for a HEAD-based symbol.

    For added_lines (HEAD coords), directly range-check against the symbol.
    For removed_lines (BASE coords), include all from any hunk whose
    added_lines overlap the symbol.
    """
    lines: list[str] = []
    for hunk in file_diff.hunks:
        hunk_overlaps = False
        for ln, content in hunk.added_lines:
            if symbol.start_line <= ln <= symbol.end_line:
                lines.append(f"+{content}")
                hunk_overlaps = True
        if hunk_overlaps:
            for _, content in hunk.removed_lines:
                lines.append(f"-{content}")
    return "\n".join(lines) if lines else None


def _symbol_overlaps_ranges(symbol: Symbol, ranges: list[tuple[int, int]]) -> bool:
    """Check if a symbol's line span overlaps any of the given ranges."""
    return any(symbol.start_line <= end and start <= symbol.end_line for start, end in ranges)


def _symbol_has_removals(file_diff: FileDiff, symbol: Symbol) -> bool:
    """Check if any removed lines fall within a BASE symbol's line range."""
    return any(
        symbol.start_line <= ln <= symbol.end_line
        for hunk in file_diff.hunks
        for ln, _ in hunk.removed_lines
    )


def _find_overlapping_range(
    symbol: Symbol, modified_ranges: list[tuple[int, int]]
) -> tuple[int, int]:
    """Find the modified range that overlaps with the symbol's line span."""
    for start, end in modified_ranges:
        if symbol.start_line <= end and start <= symbol.end_line:
            return (start, end)
    return (symbol.start_line, symbol.end_line)


def _extract_file_patches(full_diff: str) -> dict[str, str]:
    """Parse a full unified diff and extract per-file patch text.

    Returns dict mapping file_path -> patch text (hunk headers + diff lines only).
    """
    patches: dict[str, str] = {}
    # Split on "diff --git" boundaries (skip the empty first element)
    segments = full_diff.split("diff --git ")
    for segment in segments[1:]:
        # Extract the b/ path from "a/path b/path\n..."
        first_line = segment.split("\n", 1)[0]
        parts = first_line.split(" b/", 1)
        if len(parts) < 2:
            continue
        file_path = parts[1].strip()

        # Find the first hunk header and collect everything from there
        lines = segment.split("\n")
        hunk_start = None
        for i, line in enumerate(lines):
            if line.startswith("@@"):
                hunk_start = i
                break
        if hunk_start is not None:
            patches[file_path] = "\n".join(lines[hunk_start:])

    return patches


class MergeGuardEngine:
    """Top-level engine that orchestrates the full analysis pipeline."""

    def __init__(
        self,
        token: str | None = None,
        repo_full_name: str = "",
        config: MergeGuardConfig | None = None,
        *,
        client: SCMClient | None = None,
    ):
        if client is not None:
            self._client = client
        else:
            if token is None:
                raise ValueError("token is required when no client is provided")
            self._client = GitHubClient(token, repo_full_name)
        self._config = config if config is not None else MergeGuardConfig()
        self._repo_full_name = repo_full_name
        self._symbol_index = SymbolIndex()
        self._content_cache: OrderedDict[tuple[str, str], str | None] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._ignore_res = [
            _re.compile(fnmatch.translate(pat)) for pat in self._config.ignored_paths
        ]
        self._codeowners: CodeOwners | None = None  # Lazy-loaded per repo

    def _get_file_content_cached(self, path: str, ref: str) -> str | None:
        """Fetch file content with LRU caching to avoid duplicate API calls."""
        key = (path, ref)
        with self._cache_lock:
            if key in self._content_cache:
                self._content_cache.move_to_end(key)
                return self._content_cache[key]
        content = self._client.get_file_content(path, ref)
        with self._cache_lock:
            if key not in self._content_cache:
                self._content_cache[key] = content
                # Evict LRU entries if cache exceeds max size
                while len(self._content_cache) > self._config.max_cache_entries:
                    self._content_cache.popitem(last=False)
            else:
                self._content_cache.move_to_end(key)
        return self._content_cache[key]

    def _backfill_truncated_patches(self, pr: PRInfo) -> None:
        """Backfill patches for files where GitHub truncated the diff.

        GitHub REST API silently sets patch=None for files with >300 lines
        of diff. This fetches the full untruncated diff once and assigns
        patches back to the ChangedFile objects.
        """
        missing = [
            cf
            for cf in pr.changed_files
            if cf.patch is None and cf.status != FileChangeStatus.REMOVED
        ]
        if not missing:
            return

        logger.debug(
            "PR #%d has %d file(s) with truncated patches, fetching full diff",
            pr.number,
            len(missing),
        )
        try:
            full_diff = self._client.get_pr_diff(pr.number)
        except (httpx.HTTPError, SCMError):
            logger.warning(
                "Failed to fetch full diff for PR #%d, skipping backfill",
                pr.number,
                exc_info=True,
            )
            return

        file_patches = _extract_file_patches(full_diff)
        for cf in missing:
            patch = file_patches.get(cf.path)
            if patch is None and cf.previous_path:
                patch = file_patches.get(cf.previous_path)
            if patch:
                cf.patch = patch
                logger.debug("Backfilled patch for %s in PR #%d", cf.path, pr.number)

    def _resolve_conflict_owners(
        self,
        conflicts: list[Conflict],
        report: ConflictReport,
    ) -> None:
        """Resolve CODEOWNERS for each conflict and aggregate affected teams.

        Loads and caches the parsed CodeOwners object per repo.
        Sets ``conflict.owners`` and ``report.affected_teams``.
        """
        if not self._config.codeowners.enabled:
            return

        # Lazy-load and cache CODEOWNERS
        if self._codeowners is None:
            try:
                self._codeowners = load_codeowners(
                    self._client,
                    self._repo_full_name,
                    ref=report.pr.head_sha if report.pr.head_sha else "HEAD",
                )
            except (OSError, ValueError):
                logger.debug("Failed to load CODEOWNERS", exc_info=True)
                return

        if self._codeowners is None:
            return

        all_teams: set[str] = set()
        for conflict in conflicts:
            owners = self._codeowners.resolve_owners(conflict.file_path)
            conflict.owners = owners
            all_teams.update(owners)

        report.affected_teams = sorted(all_teams)

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
        logger.info("Analyzing PR #%d...", pr_number)

        # Step 1: Fetch PRs
        target_pr = self._client.get_pr(pr_number)

        # Check analysis cache (keyed by repo + PR + head SHA)
        cache = None
        cache_key = ""
        try:
            cache = AnalysisCache()
            cache_key = cache.make_key(self._repo_full_name, str(pr_number), target_pr.head_sha)
            cached = cache.get(cache_key)
            if cached is not None:
                logger.info("Cache hit for PR #%d", pr_number)
                return ConflictReport.model_validate(cached)
        except (OSError, ValueError):
            cache = None
            logger.warning("Analysis cache unavailable", exc_info=True)

        target_pr.changed_files = self._client.get_pr_files(pr_number)
        other_prs = self._client.get_open_prs(
            max_count=self._config.max_open_prs,
            max_age_days=self._config.max_pr_age_days,
        )
        logger.info("Comparing against %d open PRs", len(other_prs))

        # Detect stacked PR groups
        stack_groups: list[StackGroup] = []
        stack_lookup: dict[int, StackGroup] = {}
        if self._config.stacked_prs.enabled:
            stack_groups = detect_stacks([target_pr] + other_prs, self._config.stacked_prs)
            stack_lookup = build_stack_lookup(stack_groups)

        # Step 2: Enrich with diff data and symbols
        if hasattr(self._client, "rate_limit_remaining"):
            remaining = self._client.rate_limit_remaining
            estimated_calls = len(other_prs) * 3
            if remaining < estimated_calls:
                logger.warning(
                    "Rate limit may be insufficient: %d remaining, ~%d needed",
                    remaining,
                    estimated_calls,
                )

        self._backfill_truncated_patches(target_pr)
        self._enrich_pr(target_pr)
        prs_to_enrich = [pr for pr in other_prs if pr.number != pr_number]
        with ThreadPoolExecutor(max_workers=min(8, len(prs_to_enrich) or 1)) as executor:
            futures = {executor.submit(self._fetch_and_enrich_pr, pr): pr for pr in prs_to_enrich}
            try:
                for future in as_completed(futures, timeout=300):
                    try:
                        future.result(timeout=1)
                    except Exception:
                        logger.warning("Partial failure enriching PR", exc_info=True)
            except TimeoutError:
                logger.warning("Timeout enriching PRs — continuing with partial results")

        # Step 3: Detect AI attribution
        target_pr.ai_attribution = detect_attribution(target_pr)

        # Step 4: Detect conflicts
        prs_excluding_target = [p for p in other_prs if p.number != pr_number]
        all_conflicts, no_conflict_prs = self._detect_all_conflicts(
            target_pr,
            prs_excluding_target,
        )

        # Step 4c: Template-based fix suggestions (always)
        self._apply_template_suggestions(all_conflicts)

        # Step 4d: LLM semantic analysis for behavioral conflicts
        if self._config.llm_enabled:
            all_conflicts = self._apply_llm_analysis(target_pr, other_prs, all_conflicts)

        # Step 4e: LLM-enhanced fix suggestions (overrides templates for select types)
        if self._config.fix_suggestions and self._config.llm_enabled:
            try:
                self._generate_fix_suggestions(target_pr, other_prs, all_conflicts)
            except (httpx.HTTPError, ValueError, KeyError, OSError):
                logger.warning("Fix suggestion generation failed", exc_info=True)

        # Step 4f: Demote intra-stack conflicts
        if self._config.stacked_prs.enabled and self._config.stacked_prs.demote_severity:
            _demote_intra_stack_conflicts(all_conflicts, stack_lookup)

        # Step 5: Compute risk factors
        dependency_depth = self._compute_dependency_depth(target_pr)
        churn_score = self._compute_churn_score(target_pr)
        pattern_deviation_score = self._compute_pattern_deviation(target_pr)

        risk_score, risk_factors = compute_risk_score(
            pr=target_pr,
            conflicts=all_conflicts,
            dependency_depth=dependency_depth,
            churn_score=churn_score,
            pattern_deviation_score=pattern_deviation_score,
            config=self._config,
        )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "Found %d conflicts (risk: %.0f/100) in %dms",
            len(all_conflicts),
            risk_score,
            elapsed_ms,
        )

        target_stack = stack_lookup.get(pr_number)
        report = ConflictReport(
            pr=target_pr,
            conflicts=all_conflicts,
            risk_score=risk_score,
            risk_factors=risk_factors,
            no_conflict_prs=no_conflict_prs,
            analysis_duration_ms=elapsed_ms,
            stack_group=target_stack.group_id if target_stack else None,
            stack_position=(target_stack.pr_numbers.index(pr_number) + 1 if target_stack else None),
            stack_pr_numbers=target_stack.pr_numbers if target_stack else [],
        )

        # Resolve CODEOWNERS for conflict routing
        self._resolve_conflict_owners(all_conflicts, report)

        # Cache the result for future runs
        if cache is not None:
            try:
                cache.set(cache_key, report.model_dump(mode="json"))
            except (OSError, TypeError):
                logger.debug("Failed to cache analysis result", exc_info=True)

        # Record metrics snapshot for DORA tracking
        if self._config.metrics.enabled and report.conflicts:
            try:
                from mergeguard.core.metrics import record_analysis

                record_analysis(report, self._repo_full_name)
            except (OSError, sqlite3.Error):
                logger.debug("Failed to record metrics snapshot", exc_info=True)

        return report

    def scan_secrets_only(self, pr_number: int) -> ConflictReport:
        """Fast path: fetch only the target PR diff and run secret scanning.

        Skips conflict detection, blast radius, and policy evaluation.
        """
        from mergeguard.core.secrets import scan_secrets

        start_time = time.monotonic()
        target_pr = self._client.get_pr(pr_number)
        target_pr.changed_files = self._client.get_pr_files(pr_number)
        self._backfill_truncated_patches(target_pr)

        secret_conflicts = scan_secrets(target_pr, self._config)
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        return ConflictReport(
            pr=target_pr,
            conflicts=secret_conflicts,
            risk_score=0.0,
            risk_factors={},
            no_conflict_prs=[],
            analysis_duration_ms=elapsed_ms,
        )

    def analyze_pr_targeted(
        self,
        pr_number: int,
        existing_prs: list[PRInfo] | None = None,
    ) -> ConflictReport:
        """Targeted analysis: analyze a single PR against provided open PRs.

        When `existing_prs` is provided, skips the get_open_prs() call and only
        enriches PRs that haven't been enriched yet. This is the fast path for
        webhook-triggered analysis where the server already knows the open PRs.

        Falls back to full `analyze_pr()` when `existing_prs` is not provided.
        """
        if existing_prs is None:
            return self.analyze_pr(pr_number)

        start_time = time.monotonic()
        logger.info("Targeted analysis for PR #%d against %d PRs", pr_number, len(existing_prs))

        target_pr = self._client.get_pr(pr_number)
        target_pr.changed_files = self._client.get_pr_files(pr_number)
        self._backfill_truncated_patches(target_pr)
        self._enrich_pr(target_pr)
        target_pr.ai_attribution = detect_attribution(target_pr)

        # Enrich others that need it (those without changed_symbols)
        unenriched = [
            pr for pr in existing_prs if pr.number != pr_number and not pr.changed_symbols
        ]
        if unenriched:
            with ThreadPoolExecutor(max_workers=min(8, len(unenriched))) as executor:
                futures = {executor.submit(self._fetch_and_enrich_pr, pr): pr for pr in unenriched}
                try:
                    for future in as_completed(futures, timeout=300):
                        try:
                            future.result(timeout=1)
                        except Exception:
                            logger.warning("Partial failure enriching PR", exc_info=True)
                except TimeoutError:
                    logger.warning("Timeout enriching PRs — continuing with partial results")

        # Detect stacked PR groups
        stack_groups: list[StackGroup] = []
        stack_lookup: dict[int, StackGroup] = {}
        if self._config.stacked_prs.enabled:
            stack_groups = detect_stacks([target_pr] + existing_prs, self._config.stacked_prs)
            stack_lookup = build_stack_lookup(stack_groups)

        prs_excluding_target = [p for p in existing_prs if p.number != pr_number]
        all_conflicts, no_conflict_prs = self._detect_all_conflicts(target_pr, prs_excluding_target)
        self._apply_template_suggestions(all_conflicts)

        # Demote intra-stack conflicts
        if self._config.stacked_prs.enabled and self._config.stacked_prs.demote_severity:
            _demote_intra_stack_conflicts(all_conflicts, stack_lookup)

        dependency_depth = self._compute_dependency_depth(target_pr)
        churn_score = self._compute_churn_score(target_pr)
        pattern_deviation_score = self._compute_pattern_deviation(target_pr)

        risk_score, risk_factors = compute_risk_score(
            pr=target_pr,
            conflicts=all_conflicts,
            dependency_depth=dependency_depth,
            churn_score=churn_score,
            pattern_deviation_score=pattern_deviation_score,
            config=self._config,
        )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        target_stack = stack_lookup.get(pr_number)
        report = ConflictReport(
            pr=target_pr,
            conflicts=all_conflicts,
            risk_score=risk_score,
            risk_factors=risk_factors,
            no_conflict_prs=no_conflict_prs,
            analysis_duration_ms=elapsed_ms,
            stack_group=target_stack.group_id if target_stack else None,
            stack_position=(target_stack.pr_numbers.index(pr_number) + 1 if target_stack else None),
            stack_pr_numbers=target_stack.pr_numbers if target_stack else [],
        )

        # Resolve CODEOWNERS for conflict routing
        self._resolve_conflict_owners(all_conflicts, report)

        return report

    def analyze_all_open_prs(self) -> list[ConflictReport]:
        """Batch: fetch and enrich all PRs once, then run pairwise conflict detection."""
        all_prs = self._client.get_open_prs(
            max_count=self._config.max_open_prs,
            max_age_days=self._config.max_pr_age_days,
        )
        logger.info("Batch analysis: %d open PRs", len(all_prs))

        # Enrich each PR once (parallel)
        with ThreadPoolExecutor(max_workers=min(8, len(all_prs) or 1)) as executor:
            futures = {executor.submit(self._fetch_and_enrich_pr, pr): pr for pr in all_prs}
            try:
                for future in as_completed(futures, timeout=300):
                    try:
                        future.result(timeout=1)
                    except Exception:
                        logger.warning("Partial failure enriching PR", exc_info=True)
            except TimeoutError:
                logger.warning("Timeout enriching PRs — continuing with partial results")

        for pr in all_prs:
            pr.ai_attribution = detect_attribution(pr)

        # Detect stacked PR groups once for all PRs
        stack_groups: list[StackGroup] = []
        stack_lookup: dict[int, StackGroup] = {}
        if self._config.stacked_prs.enabled:
            stack_groups = detect_stacks(all_prs, self._config.stacked_prs)
            stack_lookup = build_stack_lookup(stack_groups)

        # Set up regression detection once for all PRs
        decisions_log = None
        if self._config.check_regressions:
            try:
                decisions_log = DecisionsLog()
            except (OSError, sqlite3.Error):
                logger.debug("Regression detection unavailable for batch", exc_info=True)

        # Run pairwise conflict detection
        reports = []
        for target_pr in all_prs:
            start = time.monotonic()
            other_prs = [p for p in all_prs if p.number != target_pr.number]

            all_conflicts, no_conflict_prs = self._detect_all_conflicts(
                target_pr,
                other_prs,
                decisions_log=decisions_log,
            )

            # Demote intra-stack conflicts
            if self._config.stacked_prs.enabled and self._config.stacked_prs.demote_severity:
                _demote_intra_stack_conflicts(all_conflicts, stack_lookup)

            dep_depth = self._compute_dependency_depth(target_pr)
            churn = self._compute_churn_score(target_pr)
            deviation = self._compute_pattern_deviation(target_pr)
            risk_score, risk_factors = compute_risk_score(
                pr=target_pr,
                conflicts=all_conflicts,
                dependency_depth=dep_depth,
                churn_score=churn,
                pattern_deviation_score=deviation,
                config=self._config,
            )

            target_stack = stack_lookup.get(target_pr.number)
            report = ConflictReport(
                pr=target_pr,
                conflicts=all_conflicts,
                risk_score=risk_score,
                risk_factors=risk_factors,
                no_conflict_prs=no_conflict_prs,
                analysis_duration_ms=int((time.monotonic() - start) * 1000),
                stack_group=target_stack.group_id if target_stack else None,
                stack_position=(
                    target_stack.pr_numbers.index(target_pr.number) + 1 if target_stack else None
                ),
                stack_pr_numbers=target_stack.pr_numbers if target_stack else [],
            )

            # Resolve CODEOWNERS for conflict routing
            self._resolve_conflict_owners(all_conflicts, report)

            reports.append(report)

        if decisions_log is not None:
            decisions_log.close()

        return reports

    @staticmethod
    def _file_path_module_forms(file_path: str) -> list[str]:
        """Convert a .py file path to dotted module name forms.

        Given ``src/mergeguard/core/conflict.py``, returns::

            ["src.mergeguard.core.conflict", "mergeguard.core.conflict",
             "core.conflict"]

        Single-segment forms (e.g., "conflict") and package-level forms
        (e.g., "mergeguard.core") are excluded because they create
        ambiguous matches in the dependency graph — a bare "conflict"
        could match unrelated imports, and "fastapi" as a package form
        would match imports from __init__.py, not the specific file.

        Returns an empty list for non-Python files.
        """
        if not file_path.endswith(".py"):
            return []
        parts = list(PurePosixPath(file_path).with_suffix("").parts)
        # Only include forms with 2+ segments to avoid ambiguous matches
        return [".".join(parts[i:]) for i in range(len(parts)) if len(parts) - i >= 2]

    def _compute_dependency_depth(self, pr: PRInfo) -> int:
        """Compute the max dependency depth across all changed files."""
        logger.debug("Computing dependency depth for PR #%d", pr.number)
        file_contents: list[tuple[str, str]] = []
        for cf in pr.changed_files:
            content = self._get_file_content_cached(cf.path, pr.base_branch)
            if content:
                file_contents.append((cf.path, content))
        if not file_contents:
            return 0
        graph = build_dependency_graph(file_contents)
        # Query depth using both the real file path and the module-form
        # (e.g., "src/utils.py" → "src.utils") since Python imports use
        # dotted module names rather than file paths.
        changed_paths = [cf.path for cf in pr.changed_files]
        max_depth = 0
        for fp in changed_paths:
            depth = graph.dependency_depth(fp)
            for module_form in self._file_path_module_forms(fp):
                depth = max(depth, graph.dependency_depth(module_form))
            max_depth = max(max_depth, depth)
        return max_depth

    def build_file_dependency_graph(self, prs: list[PRInfo]) -> DependencyGraph:
        """Build a file-level dependency graph for the given PRs.

        Public wrapper around _build_cross_pr_dependency_graph for use
        by blast radius visualization.
        """
        if not prs:
            return DependencyGraph()
        return self._build_cross_pr_dependency_graph(prs[0], prs[1:])

    def _build_cross_pr_dependency_graph(
        self,
        target_pr: PRInfo,
        other_prs: list[PRInfo],
    ) -> DependencyGraph:
        """Build a single dependency graph covering files from all PRs."""
        file_contents: list[tuple[str, str]] = []
        seen: set[str] = set()
        for pr in [target_pr, *other_prs]:
            for cf in pr.changed_files:
                if cf.path in seen:
                    continue
                seen.add(cf.path)
                content = self._get_file_content_cached(cf.path, pr.base_branch)
                # For newly added files, base branch won't have the content.
                # Fall back to head branch so we capture imports from new files.
                if not content:
                    content = self._get_file_content_cached(cf.path, pr.head_branch)
                if content:
                    file_contents.append((cf.path, content))
        return build_dependency_graph(file_contents)

    def _find_upstream_file(
        self,
        dependent_path: str,
        upstream_pr: PRInfo,
        graph: DependencyGraph,
    ) -> str:
        """Find which upstream_pr file the dependent_path imports from."""
        direct_imports = graph.get_direct_imports(dependent_path)
        for tcf in upstream_pr.changed_files:
            if tcf.path in direct_imports:
                return tcf.path
            for mf in self._file_path_module_forms(tcf.path):
                if mf in direct_imports:
                    return tcf.path
        # Fallback: return first changed file (indirect/multi-hop dependency)
        return upstream_pr.changed_files[0].path

    def _build_transitive_detail(
        self,
        dependent_file: str,
        upstream_pr: PRInfo,
        upstream_file: str,
        graph: DependencyGraph,
    ) -> tuple[list[str], list[str]]:
        """Return (changed_symbol_descriptions, specifically_imported_names).

        changed_symbol_descriptions: e.g., ["`User` (class, signature changed)"]
        specifically_imported_names: subset of imported names that overlap with changed symbols
        """
        # 1. Filter upstream_pr.changed_symbols to those in upstream_file
        file_symbols = [
            cs for cs in upstream_pr.changed_symbols if cs.symbol.file_path == upstream_file
        ]

        # 2. Format each as `name` (type[, signature changed])
        changed_descs: list[str] = []
        changed_names: set[str] = set()
        for cs in file_symbols:
            desc = f"`{cs.symbol.name}` ({cs.symbol.symbol_type.value}"
            if cs.change_type == "modified_signature":
                desc += ", signature changed"
            desc += ")"
            changed_descs.append(desc)
            changed_names.add(cs.symbol.name)

        # 3. Look up imported names - try direct path and module forms
        imported_names = graph.get_imported_names(dependent_file, upstream_file)
        if not imported_names:
            for mf in self._file_path_module_forms(upstream_file):
                imported_names = graph.get_imported_names(dependent_file, mf)
                if imported_names:
                    break

        # 4. Intersect imported names with changed symbol names
        specifically_imported = [n for n in imported_names if n in changed_names]

        return changed_descs, specifically_imported

    @staticmethod
    def _format_skipped_transitive_desc(
        skipped_prs: list[int], file_path: str, source_pr_num: int
    ) -> str:
        """Format description for capped transitive conflicts."""
        pr_list = ", ".join(f"#{n}" for n in skipped_prs[:5])
        suffix = (
            f" and {len(skipped_prs) - 5} more"
            if len(skipped_prs) > 5
            else ""
        )
        return (
            f"{len(skipped_prs)} additional PR(s) also depend on "
            f"`{file_path}` (changed by PR #{source_pr_num}): "
            f"{pr_list}{suffix}."
        )

    def _detect_transitive_conflicts(
        self,
        target_pr: PRInfo,
        other_prs: list[PRInfo],
        existing_conflicts: list[Conflict],
        graph: DependencyGraph | None = None,
    ) -> list[Conflict]:
        """Detect transitive conflicts through the dependency graph.

        A transitive conflict occurs when PR A modifies file X, PR B modifies
        file Y, and Y depends on X (or vice versa) — even though the PRs
        share no files directly.

        Checks both directions:
        - Direction A: other_pr's files depend on target_pr's files
        - Direction B: target_pr's files depend on other_pr's files
        """
        if not other_prs:
            return []

        if graph is None:
            graph = self._build_cross_pr_dependency_graph(target_pr, other_prs)

        # Skip pairs that already have a direct conflict
        existing_pairs: set[int] = set()
        for c in existing_conflicts:
            if c.conflict_type in (
                ConflictType.HARD,
                ConflictType.BEHAVIORAL,
                ConflictType.INTERFACE,
            ):
                existing_pairs.add(c.target_pr)

        # Local cache for BFS results to avoid redundant traversals
        _dep_cache: dict[str, set[str]] = {}

        max_depth = self._config.max_transitive_depth

        def _cached_get_dependents(path: str) -> set[str]:
            if path not in _dep_cache:
                _dep_cache[path] = graph.get_dependents(path, max_depth=max_depth)
            return _dep_cache[path]

        # --- Direction A: other_pr's files depend on target_pr's files ---
        target_dependents: set[str] = set()
        for cf in target_pr.changed_files:
            target_dependents |= _cached_get_dependents(cf.path)
            for module_form in self._file_path_module_forms(cf.path):
                target_dependents |= _cached_get_dependents(module_form)

        transitive: list[Conflict] = []

        # Collect hits per (other_pr, upstream_file) for aggregation
        agg_a: dict[tuple[int, str], dict[str, Any]] = {}

        for other_pr in other_prs:
            if other_pr.number in existing_pairs:
                continue
            for cf in other_pr.changed_files:
                hit = cf.path in target_dependents
                if not hit:
                    for mf in self._file_path_module_forms(cf.path):
                        if mf in target_dependents:
                            hit = True
                            break
                if hit:
                    upstream_file = self._find_upstream_file(
                        cf.path,
                        target_pr,
                        graph,
                    )
                    changed_syms, imported_syms = self._build_transitive_detail(
                        cf.path,
                        target_pr,
                        upstream_file,
                        graph,
                    )
                    key = (other_pr.number, upstream_file)
                    if key not in agg_a:
                        agg_a[key] = {
                            "other_pr": other_pr,
                            "dependent_files": [],
                            "all_imported_syms": set(),
                            "all_changed_syms": [],
                            "has_symbol_overlap": False,
                        }
                    agg_a[key]["dependent_files"].append(cf.path)
                    agg_a[key]["all_imported_syms"].update(imported_syms)
                    if not agg_a[key]["all_changed_syms"]:
                        agg_a[key]["all_changed_syms"] = changed_syms
                    if imported_syms:
                        agg_a[key]["has_symbol_overlap"] = True

        # Emit aggregated conflicts, capped per upstream file
        max_per_pair = self._config.max_transitive_per_pair

        # Group by upstream_file to cap emissions for widely-imported files
        by_upstream: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for (other_pr_num, upstream_file), info in agg_a.items():
            by_upstream.setdefault(upstream_file, []).append((other_pr_num, info))

        for upstream_file, entries in by_upstream.items():
            # Sort: symbol-overlap entries first (WARNING before INFO)
            entries.sort(key=lambda e: (not e[1]["has_symbol_overlap"], e[0]))
            emitted = 0
            skipped_prs: list[int] = []

            for other_pr_num, info in entries:
                if emitted >= max_per_pair:
                    skipped_prs.append(other_pr_num)
                    continue
                dep_files = info["dependent_files"]
                imported = sorted(info["all_imported_syms"])
                changed = info["all_changed_syms"]
                severity = (
                    ConflictSeverity.WARNING if info["has_symbol_overlap"]
                    else ConflictSeverity.INFO
                )

                if len(dep_files) == 1:
                    desc = (
                        f"PR #{other_pr_num}'s `{dep_files[0]}` depends on "
                        f"`{upstream_file}` (changed by PR #{target_pr.number})."
                    )
                else:
                    shown = ", ".join(f"`{f}`" for f in dep_files[:3])
                    more = f" and {len(dep_files) - 3} more" if len(dep_files) > 3 else ""
                    desc = (
                        f"{len(dep_files)} files in PR #{other_pr_num} depend on "
                        f"`{upstream_file}` (changed by PR #{target_pr.number}): "
                        f"{shown}{more}."
                    )
                if imported:
                    desc += f" Imports: {', '.join(f'`{n}`' for n in imported)}."
                if changed:
                    desc += f" Changed symbols: {', '.join(changed)}."

                rec = f"Review changes to {upstream_file} in PR #{target_pr.number}"
                if imported:
                    rec += f" — specifically {', '.join(f'`{n}`' for n in imported)}"
                rec += f" for compatibility with PR #{other_pr_num}."

                transitive.append(
                    Conflict(
                        conflict_type=ConflictType.TRANSITIVE,
                        severity=severity,
                        source_pr=target_pr.number,
                        target_pr=other_pr_num,
                        file_path=upstream_file,
                        symbol_name=imported[0] if len(imported) == 1 else None,
                        description=desc,
                        recommendation=rec,
                    )
                )
                emitted += 1

            # Summary conflict for skipped PRs
            if skipped_prs:
                transitive.append(
                    Conflict(
                        conflict_type=ConflictType.TRANSITIVE,
                        severity=ConflictSeverity.INFO,
                        source_pr=target_pr.number,
                        target_pr=skipped_prs[0],
                        file_path=upstream_file,
                        description=self._format_skipped_transitive_desc(
                            skipped_prs, upstream_file, target_pr.number
                        ),
                        recommendation=(
                            f"Review changes to {upstream_file} in PR #{target_pr.number} "
                            f"for broad impact — {len(skipped_prs) + emitted} PRs depend on it."
                        ),
                    )
                )

        # Track PR numbers already covered in Direction A to avoid duplicates
        direction_a_prs = {c.target_pr for c in transitive}

        # --- Direction B: target_pr's files depend on other_pr's files ---
        agg_b: dict[tuple[int, str], dict[str, Any]] = {}

        for other_pr in other_prs:
            if other_pr.number in existing_pairs:
                continue
            if other_pr.number in direction_a_prs:
                continue
            other_dependents: set[str] = set()
            for cf in other_pr.changed_files:
                other_dependents |= _cached_get_dependents(cf.path)
                for module_form in self._file_path_module_forms(cf.path):
                    other_dependents |= _cached_get_dependents(module_form)
            for cf in target_pr.changed_files:
                hit = cf.path in other_dependents
                if not hit:
                    for mf in self._file_path_module_forms(cf.path):
                        if mf in other_dependents:
                            hit = True
                            break
                if hit:
                    linking_file = other_pr.changed_files[0].path
                    for ocf in other_pr.changed_files:
                        deps = _cached_get_dependents(ocf.path)
                        for module_form in self._file_path_module_forms(ocf.path):
                            deps |= _cached_get_dependents(module_form)
                        if cf.path in deps or any(
                            mf in deps for mf in self._file_path_module_forms(cf.path)
                        ):
                            linking_file = ocf.path
                            break
                    changed_syms_b, imported_syms_b = self._build_transitive_detail(
                        cf.path,
                        other_pr,
                        linking_file,
                        graph,
                    )
                    key_b = (other_pr.number, linking_file)
                    if key_b not in agg_b:
                        agg_b[key_b] = {
                            "other_pr": other_pr,
                            "dependent_files": [],
                            "all_imported_syms": set(),
                            "all_changed_syms": [],
                            "has_symbol_overlap": False,
                        }
                    agg_b[key_b]["dependent_files"].append(cf.path)
                    agg_b[key_b]["all_imported_syms"].update(imported_syms_b)
                    if not agg_b[key_b]["all_changed_syms"]:
                        agg_b[key_b]["all_changed_syms"] = changed_syms_b
                    if imported_syms_b:
                        agg_b[key_b]["has_symbol_overlap"] = True

        # Emit Direction B, capped per linking file
        by_linking: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for (other_pr_num, linking_file), info in agg_b.items():
            by_linking.setdefault(linking_file, []).append((other_pr_num, info))

        for linking_file, entries_b in by_linking.items():
            entries_b.sort(key=lambda e: (not e[1]["has_symbol_overlap"], e[0]))
            emitted_b = 0
            skipped_b: list[int] = []

            for other_pr_num, info in entries_b:
                if emitted_b >= max_per_pair:
                    skipped_b.append(other_pr_num)
                    continue
                dep_files = info["dependent_files"]
                imported = sorted(info["all_imported_syms"])
                changed = info["all_changed_syms"]
                severity_b = (
                    ConflictSeverity.WARNING if info["has_symbol_overlap"]
                    else ConflictSeverity.INFO
                )

                if len(dep_files) == 1:
                    desc_b = (
                        f"PR #{target_pr.number}'s `{dep_files[0]}` depends on "
                        f"`{linking_file}` (changed by PR #{other_pr_num})."
                    )
                else:
                    shown = ", ".join(f"`{f}`" for f in dep_files[:3])
                    more = f" and {len(dep_files) - 3} more" if len(dep_files) > 3 else ""
                    desc_b = (
                        f"{len(dep_files)} files in PR #{target_pr.number} depend on "
                        f"`{linking_file}` (changed by PR #{other_pr_num}): "
                        f"{shown}{more}."
                    )
                if imported:
                    desc_b += f" Imports: {', '.join(f'`{n}`' for n in imported)}."
                if changed:
                    desc_b += f" Changed symbols: {', '.join(changed)}."

                rec_b = f"Review changes to {linking_file} in PR #{other_pr_num}"
                if imported:
                    rec_b += f" — specifically {', '.join(f'`{n}`' for n in imported)}"
                rec_b += f" for compatibility with PR #{target_pr.number}."

                transitive.append(
                    Conflict(
                        conflict_type=ConflictType.TRANSITIVE,
                        severity=severity_b,
                        source_pr=target_pr.number,
                        target_pr=other_pr_num,
                        file_path=linking_file,
                        symbol_name=imported[0] if len(imported) == 1 else None,
                        description=desc_b,
                        recommendation=rec_b,
                    )
                )
                emitted_b += 1

            if skipped_b:
                transitive.append(
                    Conflict(
                        conflict_type=ConflictType.TRANSITIVE,
                        severity=ConflictSeverity.INFO,
                        source_pr=target_pr.number,
                        target_pr=skipped_b[0],
                        file_path=linking_file,
                        description=self._format_skipped_transitive_desc(
                            skipped_b, linking_file, target_pr.number
                        ),
                        recommendation=(
                            f"Review changes to {linking_file} in PR #{target_pr.number} "
                            f"for broad impact — {len(skipped_b) + emitted_b} PRs depend on it."
                        ),
                    )
                )

        # Global cap: if transitive conflicts exceed 2x max_per_pair, keep only
        # the highest-severity ones and add a summary for the rest
        global_cap = max_per_pair * 2
        if len(transitive) > global_cap:
            # Sort: WARNING before INFO, then by target_pr
            transitive.sort(
                key=lambda c: (c.severity != ConflictSeverity.WARNING, c.target_pr)
            )
            kept = transitive[:global_cap]
            dropped = transitive[global_cap:]
            dropped_prs = sorted({c.target_pr for c in dropped})
            kept.append(
                Conflict(
                    conflict_type=ConflictType.TRANSITIVE,
                    severity=ConflictSeverity.INFO,
                    source_pr=target_pr.number,
                    target_pr=dropped_prs[0],
                    file_path=target_pr.changed_files[0].path,
                    description=(
                        f"{len(dropped)} additional transitive conflict(s) across "
                        f"{len(dropped_prs)} PR(s) omitted. "
                        f"PRs: {', '.join(f'#{n}' for n in dropped_prs[:5])}"
                        + (f" and {len(dropped_prs) - 5} more" if len(dropped_prs) > 5 else "")
                        + "."
                    ),
                    recommendation=(
                        "Consider reviewing the most critical conflicts above. "
                        "Run with a higher max_transitive_per_pair to see all."
                    ),
                )
            )
            transitive = kept

        return transitive

    def _compute_churn_score(self, pr: PRInfo) -> float:
        """Heuristic churn score from PR additions + deletions.

        Normalizes total line changes so that CHURN_MAX_LINES+ lines = max churn (1.0).
        """
        total_changes = sum(cf.additions + cf.deletions for cf in pr.changed_files)
        return min(1.0, total_changes / self._config.churn_max_lines)

    def _compute_pattern_deviation(self, pr: PRInfo) -> float:
        """Compute pattern deviation as 1 - symbol_name_similarity.

        Only novel symbol names (not already in the base) contribute to
        deviation.  Modifying existing symbols is 0% deviation by definition.
        """
        new_symbols = [cs.symbol for cs in pr.changed_symbols]
        if not new_symbols:
            return 0.0

        # Collect base-branch symbols for the same files
        base_symbols: list[Symbol] = []
        seen_files: set[str] = set()
        for cs in pr.changed_symbols:
            fp = cs.symbol.file_path
            if fp in seen_files:
                continue
            seen_files.add(fp)
            symbols = self._symbol_index.get_symbols(
                fp,
                self._get_file_content_cached(fp, pr.base_branch) or "",
                pr.base_branch,
            )
            base_symbols.extend(symbols)

        if not base_symbols:
            return 0.0

        # Only novel names contribute to deviation
        base_names = {s.name for s in base_symbols}
        novel_symbols = [s for s in new_symbols if s.name not in base_names]
        if not novel_symbols:
            return 0.0  # All symbols already exist in base → zero deviation

        similarity = symbol_name_similarity(novel_symbols, base_symbols)
        return 1.0 - similarity

    def _detect_cross_file_conflicts(
        self,
        target_pr: PRInfo,
        other_prs: list[PRInfo],
        existing_conflicts: list[Conflict],
        graph: DependencyGraph | None = None,
    ) -> list[Conflict]:
        """Detect conflicts across different files via import/symbol analysis.

        For each changed symbol in target_pr with change_type == "modified_signature",
        check if any other PR's files import that symbol by name → INTERFACE conflict.

        For change_type == "modified_body", check if any other PR's functions
        call the changed symbol cross-file → BEHAVIORAL conflict.
        """
        if not other_prs:
            return []

        if graph is None:
            graph = self._build_cross_pr_dependency_graph(target_pr, other_prs)
        cross_file_conflicts: list[Conflict] = []

        # Build index of other PRs' changed files for quick lookup
        other_pr_file_index: dict[str, list[PRInfo]] = {}
        for opr in other_prs:
            for cf in opr.changed_files:
                other_pr_file_index.setdefault(cf.path, []).append(opr)

        # Already-detected pairs to avoid duplicates
        existing_pairs: set[tuple[int, str, str | None]] = {
            (c.target_pr, c.file_path, c.symbol_name) for c in existing_conflicts
        }

        for cs in target_pr.changed_symbols:
            symbol_name = cs.symbol.name
            source_file = cs.symbol.file_path

            # Find all files that import this symbol (by name)
            importers = graph.get_files_importing_symbol(source_file, symbol_name)
            # Also check module-form paths
            for mf in self._file_path_module_forms(source_file):
                importers |= graph.get_files_importing_symbol(mf, symbol_name)

            # For methods, also find files importing the parent class.
            # e.g., if `Runnable.invoke` signature changed, find files that
            # `from pkg import Runnable` and call `.invoke()` on instances.
            if cs.symbol.parent and cs.symbol.symbol_type == SymbolType.METHOD:
                importers |= graph.get_files_importing_symbol(source_file, cs.symbol.parent)
                for mf in self._file_path_module_forms(source_file):
                    importers |= graph.get_files_importing_symbol(mf, cs.symbol.parent)

            if not importers:
                continue

            for importer_file in importers:
                # Find which other PRs change this importing file
                importing_prs = other_pr_file_index.get(importer_file, [])
                for other_pr in importing_prs:
                    if other_pr.number == target_pr.number:
                        continue

                    pair_key = (other_pr.number, source_file, symbol_name)
                    if pair_key in existing_pairs:
                        continue
                    existing_pairs.add(pair_key)

                    if cs.change_type == "modified_signature":
                        cross_file_conflicts.append(
                            Conflict(
                                conflict_type=ConflictType.INTERFACE,
                                severity=ConflictSeverity.CRITICAL,
                                source_pr=target_pr.number,
                                target_pr=other_pr.number,
                                file_path=source_file,
                                symbol_name=symbol_name,
                                description=(
                                    f"PR #{target_pr.number} changes the signature of "
                                    f"`{symbol_name}` in `{source_file}`, but "
                                    f"PR #{other_pr.number} modifies `{importer_file}` "
                                    f"which imports `{symbol_name}`."
                                ),
                                recommendation=(
                                    f"Update usages of `{symbol_name}` in "
                                    f"`{importer_file}` (PR #{other_pr.number}) to match "
                                    f"the new signature, or merge PR #{target_pr.number} "
                                    f"first and rebase."
                                ),
                                cross_file=True,
                            )
                        )
                    elif cs.change_type == "modified_body":
                        # Check if any of other_pr's changed symbols in importer_file
                        # reference the changed symbol
                        has_caller = any(
                            ocs.symbol.file_path == importer_file
                            and symbol_name in ocs.symbol.dependencies
                            for ocs in other_pr.changed_symbols
                        )
                        if has_caller:
                            cross_file_conflicts.append(
                                Conflict(
                                    conflict_type=ConflictType.BEHAVIORAL,
                                    severity=ConflictSeverity.WARNING,
                                    source_pr=target_pr.number,
                                    target_pr=other_pr.number,
                                    file_path=source_file,
                                    symbol_name=symbol_name,
                                    description=(
                                        f"PR #{target_pr.number} modifies the body of "
                                        f"`{symbol_name}` in `{source_file}`. "
                                        f"PR #{other_pr.number} modifies callers of "
                                        f"`{symbol_name}` in `{importer_file}`. "
                                        f"Changes may interact unexpectedly."
                                    ),
                                    recommendation=(
                                        f"Test changes to `{symbol_name}` together with "
                                        f"the caller changes in `{importer_file}` before "
                                        f"merging either PR."
                                    ),
                                    cross_file=True,
                                )
                            )

        return cross_file_conflicts

    def _detect_all_conflicts(
        self,
        target_pr: PRInfo,
        other_prs: list[PRInfo],
        decisions_log: DecisionsLog | None = None,
    ) -> tuple[list[Conflict], list[int]]:
        """Run conflict detection, guardrails, and regression checks for a PR."""
        all_conflicts: list[Conflict] = []
        no_conflict_prs: list[int] = []
        file_overlaps = compute_file_overlaps(target_pr, other_prs)

        for other_pr in other_prs:
            overlaps = file_overlaps.get(other_pr.number, [])
            if not overlaps:
                no_conflict_prs.append(other_pr.number)
                continue
            conflicts = classify_conflicts(target_pr, other_pr, overlaps)
            all_conflicts.extend(conflicts)
            if not conflicts:
                no_conflict_prs.append(other_pr.number)

        # Build dependency graph once for both cross-file and transitive detection
        dep_graph = (
            self._build_cross_pr_dependency_graph(target_pr, other_prs) if other_prs else None
        )

        # Cross-file conflict detection (symbol-level imports)
        cross_file = self._detect_cross_file_conflicts(
            target_pr,
            other_prs,
            all_conflicts,
            graph=dep_graph,
        )
        all_conflicts.extend(cross_file)
        cross_file_prs = {c.target_pr for c in cross_file}
        no_conflict_prs = [n for n in no_conflict_prs if n not in cross_file_prs]

        # Transitive conflict detection
        transitive = self._detect_transitive_conflicts(
            target_pr,
            other_prs,
            all_conflicts,
            graph=dep_graph,
        )
        all_conflicts.extend(transitive)
        transitive_prs = {c.target_pr for c in transitive}
        no_conflict_prs = [n for n in no_conflict_prs if n not in transitive_prs]

        # Guardrails
        if self._config.rules:
            all_conflicts.extend(enforce_guardrails(target_pr, self._config))

        # Secret scanning
        if self._config.secrets.enabled:
            from mergeguard.core.secrets import scan_secrets

            all_conflicts.extend(scan_secrets(target_pr, self._config))

        # Regression detection
        own_log = False
        if decisions_log is None and self._config.check_regressions:
            try:
                decisions_log = DecisionsLog()
                own_log = True
            except (OSError, sqlite3.Error):
                logger.warning("Regression detection skipped", exc_info=True)
        if decisions_log is not None:
            try:
                all_conflicts.extend(detect_regressions(target_pr, decisions_log))
            except (OSError, sqlite3.Error):
                logger.debug(
                    "Regression detection failed for PR #%d",
                    target_pr.number,
                    exc_info=True,
                )
            if own_log:
                decisions_log.close()

        return all_conflicts, no_conflict_prs

    def _fetch_and_enrich_pr(self, pr: PRInfo) -> None:
        """Fetch files and enrich a PR. Safe for concurrent execution."""
        try:
            pr.changed_files = self._client.get_pr_files(pr.number)
            self._backfill_truncated_patches(pr)
            self._enrich_pr(pr)
        except (httpx.HTTPError, SCMError):
            logger.warning("Failed to enrich PR #%d, skipping", pr.number, exc_info=True)

    def _create_llm_analyzer(self) -> LLMAnalyzer | None:
        """Create an LLMAnalyzer if an API key is available, or return None."""
        from mergeguard.integrations.llm_analyzer import _resolve_provider

        provider = _resolve_provider(self._config.llm_provider)
        if provider is None:
            logger.warning(
                "LLM analysis enabled but no API key set (set OPENAI_API_KEY or ANTHROPIC_API_KEY)"
            )
            return None

        try:
            from mergeguard.integrations.llm_analyzer import LLMAnalyzer
        except ImportError:
            logger.warning("LLM analysis enabled but required LLM package not installed")
            return None

        try:
            return LLMAnalyzer(
                model=self._config.llm_model
                if self._config.llm_model != "claude-sonnet-4-20250514" or provider == "anthropic"
                else None,
                provider=self._config.llm_provider,
            )
        except (ImportError, ValueError, TypeError):
            logger.warning("Failed to initialize LLM analyzer", exc_info=True)
            return None

    def _apply_template_suggestions(self, conflicts: list[Conflict]) -> None:
        """Apply template-based fix suggestions to all conflicts (zero cost)."""
        from mergeguard.core.fix_templates import generate_template_suggestion

        for conflict in conflicts:
            suggestion = generate_template_suggestion(conflict)
            if suggestion:
                conflict.fix_suggestion = suggestion

    def _apply_llm_analysis(
        self,
        target_pr: PRInfo,
        other_prs: list[PRInfo],
        conflicts: list[Conflict],
    ) -> list[Conflict]:
        """Use LLM to refine behavioral conflict severity.

        Uses holistic batch mode when > 3 conflicts exist for a target PR.
        """
        llm = self._create_llm_analyzer()
        if llm is None:
            return conflicts

        other_pr_map = {pr.number: pr for pr in other_prs}

        # Group conflicts by target PR for potential holistic analysis
        from collections import defaultdict

        by_target: dict[int, list[Conflict]] = defaultdict(list)
        for conflict in conflicts:
            by_target[conflict.target_pr].append(conflict)

        for target_pr_num, group in by_target.items():
            # Holistic batch mode when > 3 conflicts per target PR
            if len(group) > 3:
                try:
                    llm.analyze_conflict_batch(group)
                except (httpx.HTTPError, ValueError, KeyError, OSError):
                    logger.debug(
                        "Holistic LLM analysis failed for PR #%d",
                        target_pr_num,
                        exc_info=True,
                    )
                continue

            # Individual analysis for smaller groups — parallelize LLM calls
            behavioral = [
                c
                for c in group
                if c.conflict_type == ConflictType.BEHAVIORAL
                and c.symbol_name
                and other_pr_map.get(c.target_pr)
            ]

            def _analyze_single(conflict: Conflict) -> None:
                other_pr = other_pr_map[conflict.target_pr]
                symbol = conflict.symbol_name
                if symbol is None:
                    return
                source_diff = self._get_symbol_diff(target_pr, symbol, conflict.file_path)
                target_diff = self._get_symbol_diff(other_pr, symbol, conflict.file_path)
                if not source_diff or not target_diff:
                    return
                llm_result = llm.analyze_behavioral_conflict(
                    symbol_name=symbol,
                    file_path=conflict.file_path,
                    pr_a_number=conflict.source_pr,
                    pr_a_diff=source_diff,
                    pr_b_number=conflict.target_pr,
                    pr_b_diff=target_diff,
                )
                if llm_result is None:
                    conflict.severity = ConflictSeverity.INFO
                    conflict.description += " (LLM: changes are compatible)"
                else:
                    conflict.severity = llm_result.severity
                    conflict.description = llm_result.description
                    conflict.recommendation = llm_result.recommendation

            with ThreadPoolExecutor(max_workers=min(5, len(behavioral) or 1)) as pool:
                futures = {pool.submit(_analyze_single, c): c for c in behavioral}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except (httpx.HTTPError, ValueError, KeyError):
                        c = futures[future]
                        logger.debug(
                            "LLM analysis failed for %s in %s",
                            c.symbol_name,
                            c.file_path,
                            exc_info=True,
                        )

        return conflicts

    def _generate_fix_suggestions(
        self,
        target_pr: PRInfo,
        other_prs: list[PRInfo],
        conflicts: list[Conflict],
    ) -> None:
        """Generate LLM-enhanced fix suggestions for conflicts that benefit from it.

        Only BEHAVIORAL and INTERFACE conflicts at warning/critical severity are
        sent to the LLM. Other types keep their template suggestions. Conflicts
        sharing the same (file_path, target_pr) are batched into a single LLM call.
        """
        from collections import defaultdict

        # 1. Filter to LLM-worthy conflicts
        llm_worthy = [
            c
            for c in conflicts
            if c.conflict_type in (ConflictType.BEHAVIORAL, ConflictType.INTERFACE)
            and c.severity != ConflictSeverity.INFO
        ]
        if not llm_worthy:
            return

        llm = self._create_llm_analyzer()
        if llm is None:
            return

        other_pr_map = {pr.number: pr for pr in other_prs}

        # 2. Group by (file_path, target_pr) — same diffs can be shared
        groups: dict[tuple[str, int], list[Conflict]] = defaultdict(list)
        for c in llm_worthy:
            groups[(c.file_path, c.target_pr)].append(c)

        # 3. One LLM call per group
        for (file_path, target_pr_num), group in groups.items():
            other_pr = other_pr_map.get(target_pr_num)
            if not other_pr:
                continue

            source_diff = self._get_file_diff(target_pr, file_path)
            target_diff = self._get_file_diff(other_pr, file_path)
            if not source_diff or not target_diff:
                continue

            try:
                if len(group) == 1:
                    suggestion = llm.generate_fix_suggestion(
                        conflict=group[0],
                        source_diff=source_diff,
                        target_diff=target_diff,
                    )
                    if suggestion:
                        group[0].fix_suggestion = suggestion
                else:
                    results = llm.generate_fix_suggestions_batch(
                        conflicts=group,
                        source_diff=source_diff,
                        target_diff=target_diff,
                    )
                    for conflict, suggestion in zip(group, results, strict=True):
                        if suggestion:
                            conflict.fix_suggestion = suggestion
            except (httpx.HTTPError, ValueError, KeyError, OSError):
                logger.debug(
                    "Fix suggestion failed for %s",
                    file_path,
                    exc_info=True,
                )

    def _get_symbol_diff(self, pr: PRInfo, symbol_name: str, file_path: str) -> str | None:
        """Find the raw diff for a specific symbol in a PR."""
        for cs in pr.changed_symbols:
            if cs.symbol.name == symbol_name and cs.symbol.file_path == file_path:
                return cs.raw_diff
        return None

    def _get_file_diff(self, pr: PRInfo, file_path: str) -> str | None:
        """Find the raw patch for a file in a PR."""
        for cf in pr.changed_files:
            if cf.path == file_path:
                return cf.patch
        return None

    def _parse_file_diff(
        self,
        changed_file: ChangedFile,
        pr: PRInfo,
    ) -> tuple[list[FileDiff], list[tuple[int, int]]] | None:
        """Parse a changed file's patch into structured diffs and modified ranges."""
        if not changed_file.patch:
            logger.warning("Skipping %s (no patch after backfill)", changed_file.path)
            pr.skipped_files.append(changed_file.path)
            return None

        diff_text = (
            f"diff --git a/{changed_file.path} b/{changed_file.path}\n"
            f"--- a/{changed_file.path}\n"
            f"+++ b/{changed_file.path}\n" + changed_file.patch
        )
        file_diffs = parse_unified_diff(diff_text)
        if not file_diffs:
            return None
        modified_ranges = file_diffs[0].all_modified_line_ranges
        if not modified_ranges:
            return None
        return file_diffs, modified_ranges

    def _fetch_and_validate_content(
        self,
        path: str,
        ref: str,
        max_size: int,
        pr: PRInfo,
    ) -> str | None:
        """Fetch file content, rejecting large and binary files."""
        content = self._get_file_content_cached(path, ref)
        if not content:
            return None
        if len(content) > max_size:
            logger.warning(
                "Skipping %s (%.0fKB exceeds size limit)",
                path,
                len(content) / 1024,
            )
            pr.skipped_files.append(path)
            return None
        if "\x00" in content[:8192]:
            logger.warning("Skipping %s (binary file)", path)
            pr.skipped_files.append(path)
            return None
        return content

    def _build_changed_symbols(
        self,
        pr: PRInfo,
        changed_file: ChangedFile,
        file_diffs: list[FileDiff],
        modified_ranges: list[tuple[int, int]],
        content: str,
    ) -> list[ChangedSymbol]:
        """Extract changed symbols, call graph, and signature changes for a file."""
        base_symbols, call_graph = self._symbol_index.get_symbols_and_call_graph(
            changed_file.path,
            content,
            pr.base_branch,
        )

        # Populate intra-file call graph as symbol dependencies
        for symbol in base_symbols:
            if symbol.name in call_graph:
                symbol.dependencies = list(call_graph[symbol.name])

        # Fetch head-branch content for three-way classification
        # Skip for fork PRs — head branch doesn't exist in the base repo
        if pr.is_fork:
            # Fallback: use BASE-only overlap detection (pre-existing limitation)
            result: list[ChangedSymbol] = []
            affected = map_diff_to_symbols(base_symbols, modified_ranges)
            for symbol in affected:
                raw_diff = _extract_symbol_diff(file_diffs[0], symbol)
                result.append(
                    ChangedSymbol(
                        symbol=symbol,
                        change_type="modified_body",
                        diff_lines=_find_overlapping_range(symbol, modified_ranges),
                        raw_diff=raw_diff,
                    )
                )
            return result

        head_content = self._get_file_content_cached(
            changed_file.path,
            pr.head_branch,
        )
        if not head_content:
            # No HEAD content available — fall back to BASE-only
            affected = map_diff_to_symbols(base_symbols, modified_ranges)
            result = []
            for symbol in affected:
                raw_diff = _extract_symbol_diff(file_diffs[0], symbol)
                result.append(
                    ChangedSymbol(
                        symbol=symbol,
                        change_type="modified_body",
                        diff_lines=_find_overlapping_range(symbol, modified_ranges),
                        raw_diff=raw_diff,
                    )
                )
            return result

        head_symbols, head_call_graph = self._symbol_index.get_symbols_and_call_graph(
            changed_file.path,
            head_content,
            pr.head_branch,
        )

        # Three-way classification: compare BASE vs HEAD symbols by (name, parent).
        # Use first occurrence per key (outermost definition) — later duplicates
        # are typically nested closures with the same name.
        base_by_key: dict[tuple[str, str | None], Symbol] = {}
        for s in base_symbols:
            base_by_key.setdefault((s.name, s.parent), s)
        head_by_key: dict[tuple[str, str | None], Symbol] = {}
        for s in head_symbols:
            head_by_key.setdefault((s.name, s.parent), s)
        base_keys = set(base_by_key)
        head_keys = set(head_by_key)

        result = []

        # ADDED: in HEAD only — check HEAD symbol against HEAD modified ranges
        for key in head_keys - base_keys:
            head_sym = head_by_key[key]
            if _symbol_overlaps_ranges(head_sym, modified_ranges):
                # Populate call graph for the new symbol
                if head_sym.name in head_call_graph:
                    head_sym.dependencies = list(head_call_graph[head_sym.name])
                raw_diff = _extract_symbol_diff_head(file_diffs[0], head_sym)
                result.append(
                    ChangedSymbol(
                        symbol=head_sym,
                        change_type="added",
                        diff_lines=_find_overlapping_range(head_sym, modified_ranges),
                        raw_diff=raw_diff,
                    )
                )

        # REMOVED: in BASE only — check if removed_lines fall in BASE symbol range
        for key in base_keys - head_keys:
            base_sym = base_by_key[key]
            if _symbol_has_removals(file_diffs[0], base_sym):
                raw_diff = _extract_symbol_diff(file_diffs[0], base_sym)
                result.append(
                    ChangedSymbol(
                        symbol=base_sym,
                        change_type="removed",
                        diff_lines=(base_sym.start_line, base_sym.end_line),
                        raw_diff=raw_diff,
                    )
                )

        # MODIFIED: in both — use HEAD symbol position against HEAD ranges
        for key in base_keys & head_keys:
            head_sym = head_by_key[key]
            base_sym = base_by_key[key]
            if _symbol_overlaps_ranges(head_sym, modified_ranges):
                change_type = "modified_body"
                if (
                    head_sym.signature
                    and base_sym.signature
                    and head_sym.signature != base_sym.signature
                ):
                    change_type = "modified_signature"
                    logger.debug(
                        "Signature change detected: %s in %s",
                        head_sym.name,
                        changed_file.path,
                    )
                # Carry over call graph from BASE (already populated)
                head_sym.dependencies = base_sym.dependencies
                raw_diff = _extract_symbol_diff_head(file_diffs[0], head_sym)
                result.append(
                    ChangedSymbol(
                        symbol=head_sym,
                        change_type=change_type,
                        diff_lines=_find_overlapping_range(head_sym, modified_ranges),
                        raw_diff=raw_diff,
                    )
                )

        return result

    def _enrich_pr(self, pr: PRInfo) -> None:
        """Enrich a PR with diff data and changed symbols."""
        # Filter out ignored paths before any API calls (pre-compiled patterns)
        pr.changed_files = [
            cf for cf in pr.changed_files if not any(pat.match(cf.path) for pat in self._ignore_res)
        ]

        for changed_file in pr.changed_files:
            if changed_file.status == FileChangeStatus.REMOVED:
                continue
            parsed = self._parse_file_diff(changed_file, pr)
            if parsed is None:
                continue
            file_diffs, modified_ranges = parsed
            max_file = self._config.max_file_size
            content = self._fetch_and_validate_content(
                changed_file.path,
                pr.base_branch,
                max_file,
                pr,
            )
            if content is None:
                continue
            new_symbols = self._build_changed_symbols(
                pr,
                changed_file,
                file_diffs,
                modified_ranges,
                content,
            )
            pr.changed_symbols.extend(new_symbols)
