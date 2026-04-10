"""Tests for engine module."""

from __future__ import annotations

import sys
import threading
from unittest.mock import MagicMock, patch

import pytest
from conftest import make_test_pr

from mergeguard.analysis.dependency import DependencyGraph, ImportEdge
from mergeguard.analysis.diff_parser import DiffHunk, FileDiff
from mergeguard.core.engine import (
    MergeGuardEngine,
    _extract_symbol_diff,
)
from mergeguard.models import (
    ChangedSymbol,
    Conflict,
    ConflictSeverity,
    ConflictType,
    FileChangeStatus,
    Symbol,
    SymbolType,
)


class TestModuleSuffixMatching:
    """P2: _compute_dependency_depth should try all module name suffixes."""

    def test_module_suffix_matching(self):
        """Depth is found when the file path has a repo prefix.

        The prefix doesn't match the import module name.
        """
        pr = make_test_pr(1, ["libs/partners/openai/langchain_openai/chat_models/base.py"])

        # Mock a dependency graph whose _reverse dict uses short module names
        mock_graph = MagicMock()

        def mock_depth(key):
            depths = {
                "langchain_openai.chat_models.base": 3,
            }
            return depths.get(key, 0)

        mock_graph.dependency_depth.side_effect = mock_depth

        # Mock the engine to test _compute_dependency_depth
        with patch("mergeguard.core.engine.build_dependency_graph", return_value=mock_graph):
            from mergeguard.core.engine import MergeGuardEngine

            engine = MergeGuardEngine.__new__(MergeGuardEngine)
            engine._content_cache = {}
            engine._cache_lock = __import__("threading").Lock()
            engine._symbol_index = MagicMock()

            # Mock _get_file_content_cached to return some content
            engine._get_file_content_cached = MagicMock(return_value="import os")

            depth = engine._compute_dependency_depth(pr)
            assert depth == 3

    def test_full_path_no_match_but_suffix_matches(self):
        """The full dotted path doesn't match, but a suffix does."""
        pr = make_test_pr(1, ["src/mypackage/utils.py"])

        mock_graph = MagicMock()

        def mock_depth(key):
            depths = {
                "mypackage.utils": 2,
            }
            return depths.get(key, 0)

        mock_graph.dependency_depth.side_effect = mock_depth

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=mock_graph):
            from mergeguard.core.engine import MergeGuardEngine

            engine = MergeGuardEngine.__new__(MergeGuardEngine)
            engine._content_cache = {}
            engine._cache_lock = __import__("threading").Lock()
            engine._symbol_index = MagicMock()
            engine._get_file_content_cached = MagicMock(return_value="import os")

            depth = engine._compute_dependency_depth(pr)
            assert depth == 2


class TestExtractSymbolDiff:
    """Tests for _extract_symbol_diff helper."""

    def test_extracts_lines_within_range(self):
        symbol = Symbol(
            name="func",
            symbol_type=SymbolType.FUNCTION,
            file_path="test.py",
            start_line=10,
            end_line=20,
        )
        file_diff = FileDiff(
            path="test.py",
            old_path=None,
            hunks=[
                DiffHunk(
                    old_start=10,
                    old_count=5,
                    new_start=10,
                    new_count=6,
                    added_lines=[(12, "    new_line"), (25, "    outside")],
                    removed_lines=[(11, "    old_line")],
                    context_lines=[],
                )
            ],
        )
        result = _extract_symbol_diff(file_diff, symbol)
        assert "+    new_line" in result
        assert "-    old_line" in result
        assert "outside" not in result

    def test_returns_none_when_no_overlap(self):
        symbol = Symbol(
            name="func",
            symbol_type=SymbolType.FUNCTION,
            file_path="test.py",
            start_line=100,
            end_line=110,
        )
        file_diff = FileDiff(
            path="test.py",
            old_path=None,
            hunks=[
                DiffHunk(
                    old_start=10,
                    old_count=5,
                    new_start=10,
                    new_count=6,
                    added_lines=[(12, "    line")],
                    removed_lines=[],
                    context_lines=[],
                )
            ],
        )
        result = _extract_symbol_diff(file_diff, symbol)
        assert result is None


class TestPatternDeviation:
    """Pattern deviation should be zero when all PR symbols already exist in base."""

    def _make_engine(self, base_symbols):
        """Create a minimal engine with mocked symbol index."""
        import threading

        from mergeguard.core.engine import MergeGuardEngine

        engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._content_cache = {}
        engine._cache_lock = threading.Lock()
        engine._symbol_index = MagicMock()
        engine._symbol_index.get_symbols.return_value = base_symbols
        engine._get_file_content_cached = MagicMock(return_value="content")
        return engine

    def test_pattern_deviation_zero_for_existing_symbols(self):
        """PR modifies existing functions → deviation = 0.0."""
        base_symbols = [
            Symbol(
                name="func_a",
                symbol_type=SymbolType.FUNCTION,
                file_path="src/core.py",
                start_line=1,
                end_line=10,
            ),
            Symbol(
                name="func_b",
                symbol_type=SymbolType.FUNCTION,
                file_path="src/core.py",
                start_line=20,
                end_line=30,
            ),
        ]
        engine = self._make_engine(base_symbols)

        pr = make_test_pr(1, ["src/core.py"])
        pr.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="func_a",
                    symbol_type=SymbolType.FUNCTION,
                    file_path="src/core.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_body",
                diff_lines=(5, 8),
            ),
        ]
        assert engine._compute_pattern_deviation(pr) == 0.0

    def test_pattern_deviation_high_for_novel_symbols(self):
        """PR adds new function with unusual name → deviation > 0."""
        base_symbols = [
            Symbol(
                name="process_data",
                symbol_type=SymbolType.FUNCTION,
                file_path="src/core.py",
                start_line=1,
                end_line=10,
            ),
            Symbol(
                name="validate_input",
                symbol_type=SymbolType.FUNCTION,
                file_path="src/core.py",
                start_line=20,
                end_line=30,
            ),
        ]
        engine = self._make_engine(base_symbols)

        pr = make_test_pr(1, ["src/core.py"])
        pr.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="xyzzy_quirk",
                    symbol_type=SymbolType.FUNCTION,
                    file_path="src/core.py",
                    start_line=40,
                    end_line=50,
                ),
                change_type="added",
                diff_lines=(40, 50),
            ),
        ]
        deviation = engine._compute_pattern_deviation(pr)
        assert deviation > 0


class TestCacheSymlinkRejection:
    """Cache should reject symlinked directories."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require admin on Windows")
    def test_symlink_cache_dir_raises(self, tmp_path):
        """AnalysisCache should refuse to use a symlinked directory."""
        import pytest

        from mergeguard.storage.cache import AnalysisCache

        real_dir = tmp_path / "real"
        real_dir.mkdir()
        symlink_dir = tmp_path / "symlink-cache"
        symlink_dir.symlink_to(real_dir)

        with pytest.raises(ValueError, match="symlink"):
            AnalysisCache(cache_dir=symlink_dir)

    def test_non_symlink_cache_dir_works(self, tmp_path):
        """AnalysisCache should work with a normal directory."""
        from mergeguard.storage.cache import AnalysisCache

        cache = AnalysisCache(cache_dir=tmp_path / "normal-cache")
        cache.set("key", {"value": 42})
        assert cache.get("key") == {"value": 42}


class TestEnrichPRRobustness:
    """Tests for binary/large file skipping in _enrich_pr."""

    def _make_engine(self):
        import threading
        from collections import OrderedDict

        from mergeguard.core.engine import MergeGuardEngine

        engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._content_cache = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._symbol_index = MagicMock()
        engine._symbol_index.get_symbols.return_value = []
        engine._config = MagicMock()
        engine._config.ignored_paths = []
        engine._config.max_file_size = 500_000
        engine._ignore_res = []
        engine._client = MagicMock()
        return engine

    def test_large_file_skipped(self):
        """Files exceeding 500KB should be skipped."""
        engine = self._make_engine()
        large_content = "x" * 600_000
        engine._get_file_content_cached = MagicMock(return_value=large_content)

        pr = make_test_pr(1, ["src/big.py"])
        pr.changed_files[0].patch = "@@ -1,3 +1,3 @@\n-old\n+new"
        engine._enrich_pr(pr)
        assert "src/big.py" in pr.skipped_files

    def test_binary_file_skipped(self):
        """Files with null bytes in first 8KB should be skipped."""
        engine = self._make_engine()
        binary_content = "header\x00binary_data"
        engine._get_file_content_cached = MagicMock(return_value=binary_content)

        pr = make_test_pr(1, ["src/data.bin"])
        pr.changed_files[0].patch = "@@ -1,3 +1,3 @@\n-old\n+new"
        engine._enrich_pr(pr)
        assert "src/data.bin" in pr.skipped_files

    def test_deleted_file_skipped(self):
        """Deleted files should be skipped in _enrich_pr."""
        engine = self._make_engine()
        engine._get_file_content_cached = MagicMock(return_value="content")

        pr = make_test_pr(1, ["src/removed.py"])
        pr.changed_files[0].status = FileChangeStatus.REMOVED
        pr.changed_files[0].patch = "@@ -1,3 +0,0 @@\n-old"
        engine._enrich_pr(pr)
        # Deleted files are skipped silently (no processing, not in skipped_files)
        assert len(pr.changed_symbols) == 0


class TestTransitiveConflictDetection:
    """Tests for transitive conflict detection through dependency graphs."""

    def _make_engine(self):
        from collections import OrderedDict

        engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._content_cache = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._symbol_index = MagicMock()
        engine._config = MagicMock()
        engine._config.max_transitive_per_pair = 5
        engine._config.max_transitive_depth = 1
        engine._get_file_content_cached = MagicMock(return_value="import models")
        return engine

    def _make_graph(self, edges):
        """Build a DependencyGraph from (source, target) or (source, target, names) tuples."""
        graph = DependencyGraph()
        for edge in edges:
            if len(edge) == 3:
                src, tgt, names = edge
            else:
                src, tgt = edge
                names = []
            graph.add_edge(ImportEdge(source_file=src, target_file=tgt, imported_names=names))
        return graph

    def test_basic_transitive_detected(self):
        """PR1 modifies models.py, PR2 modifies views.py which imports models.

        Expect 1 TRANSITIVE INFO (no specific symbol overlap).
        """
        engine = self._make_engine()
        target = make_test_pr(1, ["src/models.py"])
        target.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="User",
                    symbol_type=SymbolType.CLASS,
                    file_path="src/models.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_signature",
                diff_lines=(1, 10),
            ),
        ]
        other = make_test_pr(2, ["src/views.py"])

        # views.py imports src.models (stored as dotted module name)
        graph = self._make_graph([("src/views.py", "src.models")])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        assert result[0].conflict_type == ConflictType.TRANSITIVE
        assert result[0].severity == ConflictSeverity.INFO
        assert result[0].target_pr == 2
        # Description should reference the upstream file
        assert "src/models.py" in result[0].description
        assert "PR #2" in result[0].description

    def test_no_transitive_when_no_dependency(self):
        """Two PRs modify unrelated files — no transitive conflicts."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/auth.py"])
        other = make_test_pr(2, ["src/logging.py"])

        graph = self._make_graph([])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert result == []

    def test_skipped_when_direct_conflict_exists(self):
        """PRs already have a HARD conflict — no redundant transitive."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/models.py"])
        other = make_test_pr(2, ["src/views.py"])

        graph = self._make_graph([("src/views.py", "src.models")])

        existing = [
            Conflict(
                conflict_type=ConflictType.HARD,
                severity=ConflictSeverity.CRITICAL,
                source_pr=1,
                target_pr=2,
                file_path="src/models.py",
                description="direct conflict",
                recommendation="coordinate",
            )
        ]

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], existing)

        assert result == []

    def test_via_module_name_form(self):
        """Import uses dotted module name, file uses path — still detected."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/mergeguard/core/models.py"])
        other = make_test_pr(2, ["src/views.py"])

        # views.py imports "mergeguard.core.models" — the reverse edge is keyed
        # by the dotted name, not the file path
        graph = self._make_graph([("src/views.py", "mergeguard.core.models")])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        assert result[0].target_pr == 2

    def test_removes_pr_from_no_conflict_list(self):
        """PR with transitive conflict is removed from no_conflict_prs in _detect_all_conflicts."""
        engine = self._make_engine()
        engine._config = MagicMock()
        engine._config.max_transitive_per_pair = 5
        engine._config.max_transitive_depth = 1
        engine._config.rules = []
        engine._config.secrets.enabled = False
        engine._config.check_regressions = False

        target = make_test_pr(1, ["src/models.py"])
        other = make_test_pr(2, ["src/views.py"])

        graph = self._make_graph([("src/views.py", "src.models")])

        with (
            patch("mergeguard.core.engine.build_dependency_graph", return_value=graph),
            patch("mergeguard.core.engine.compute_file_overlaps", return_value={}),
            patch("mergeguard.core.engine.classify_conflicts", return_value=[]),
        ):
            conflicts, no_conflict = engine._detect_all_conflicts(target, [other])

        transitive = [c for c in conflicts if c.conflict_type == ConflictType.TRANSITIVE]
        assert len(transitive) == 1
        assert 2 not in no_conflict

    def test_empty_graph(self):
        """No imports — no transitive conflicts."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/a.py"])
        other = make_test_pr(2, ["src/b.py"])

        graph = DependencyGraph()

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert result == []

    def test_multiple_dependents(self):
        """One utility file has dependents across 3 PRs — 3 transitive conflicts."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/utils.py"])
        pr2 = make_test_pr(2, ["src/a.py"])
        pr3 = make_test_pr(3, ["src/b.py"])
        pr4 = make_test_pr(4, ["src/c.py"])

        graph = self._make_graph(
            [
                ("src/a.py", "src.utils"),
                ("src/b.py", "src.utils"),
                ("src/c.py", "src.utils"),
            ]
        )

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [pr2, pr3, pr4], [])

        assert len(result) == 3
        target_prs = {c.target_pr for c in result}
        assert target_prs == {2, 3, 4}

    def test_reverse_direction_detected(self):
        """Target modifies views.py which imports models.

        Other modifies models.py -- detected via reverse check.
        """
        engine = self._make_engine()
        target = make_test_pr(1, ["src/views.py"])
        other = make_test_pr(2, ["src/models.py"])
        other.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="User",
                    symbol_type=SymbolType.CLASS,
                    file_path="src/models.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_body",
                diff_lines=(1, 10),
            ),
        ]

        # views.py imports src.models with specific names → models has views.py as a dependent
        graph = self._make_graph([("src/views.py", "src.models", ["User"])])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        assert result[0].conflict_type == ConflictType.TRANSITIVE
        assert result[0].severity == ConflictSeverity.WARNING
        assert result[0].target_pr == 2
        # Description should reference specific symbols
        assert "src/models.py" in result[0].description
        assert "`User`" in result[0].description

    def test_no_duplicate_when_both_directions(self):
        """Graph has edges in both directions between PR files — only 1 conflict, not 2."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/a.py"])
        other = make_test_pr(2, ["src/b.py"])

        # a.py imports b and b imports a — both directions have a dependency
        graph = self._make_graph(
            [
                ("src/a.py", "src/b.py"),
                ("src/b.py", "src/a.py"),
            ]
        )

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        # Should report exactly 1 conflict (forward match), not 2
        assert len(result) == 1

    def test_deep_chain(self):
        """A imports B imports C; PR1 modifies C, PR2 modifies A — transitive detected.

        Uses consistent keys so BFS can traverse the full chain.
        Requires depth=2 since this is a 2-hop chain.
        """
        engine = self._make_engine()
        engine._config.max_transitive_depth = 2
        target = make_test_pr(1, ["src/c.py"])
        other = make_test_pr(2, ["src/a.py"])

        # a.py imports src/b.py, b.py imports src/c.py
        # BFS from src/c.py: reverse[src/c.py] = {src/b.py}, reverse[src/b.py] = {src/a.py}
        graph = self._make_graph(
            [
                ("src/a.py", "src/b.py"),
                ("src/b.py", "src/c.py"),
            ]
        )

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        assert result[0].target_pr == 2

    def test_transitive_description_includes_imported_symbols(self):
        """Description cross-references imported names with changed symbols."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/models.py"])
        target.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="User",
                    symbol_type=SymbolType.CLASS,
                    file_path="src/models.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_signature",
                diff_lines=(1, 10),
            ),
            ChangedSymbol(
                symbol=Symbol(
                    name="process_data",
                    symbol_type=SymbolType.FUNCTION,
                    file_path="src/models.py",
                    start_line=20,
                    end_line=30,
                ),
                change_type="modified_body",
                diff_lines=(20, 30),
            ),
        ]
        other = make_test_pr(2, ["src/views.py"])

        # views.py imports User from src.models
        graph = self._make_graph(
            [
                ("src/views.py", "src.models", ["User"]),
            ]
        )

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        desc = result[0].description
        # Should mention the specifically imported symbol
        assert "`User`" in desc
        # Should list changed symbols
        assert "`User` (class, signature changed)" in desc
        assert "`process_data` (function)" in desc
        # symbol_name set when exactly 1 imported symbol
        assert result[0].symbol_name == "User"
        # Recommendation should mention specific symbol
        assert "`User`" in result[0].recommendation

    def test_transitive_description_fallback_no_imported_names(self):
        """When graph edge has no imported names, description still lists changed symbols."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/models.py"])
        target.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="User",
                    symbol_type=SymbolType.CLASS,
                    file_path="src/models.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_body",
                diff_lines=(1, 10),
            ),
        ]
        other = make_test_pr(2, ["src/views.py"])

        # views.py imports src.models but without specific names (bare import edge)
        graph = self._make_graph([("src/views.py", "src.models")])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        desc = result[0].description
        # Should still list changed symbols from the upstream file
        assert "`User` (class)" in desc
        # No specific imports to list
        assert "Imports:" not in desc
        # symbol_name should be None (no imported names to cross-reference)
        assert result[0].symbol_name is None
        # No imported symbol overlap → INFO severity
        assert result[0].severity == ConflictSeverity.INFO

    def test_transitive_without_symbol_overlap_is_info(self):
        """When imported symbols don't overlap with changed symbols, severity is INFO."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/models.py"])
        target.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="Admin",
                    symbol_type=SymbolType.CLASS,
                    file_path="src/models.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_body",
                diff_lines=(1, 10),
            ),
        ]
        other = make_test_pr(2, ["src/views.py"])

        # views.py imports User from src.models — but Admin changed, not User
        graph = self._make_graph([("src/views.py", "src.models", ["User"])])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        assert result[0].severity == ConflictSeverity.INFO

    def test_transitive_with_symbol_overlap_is_warning(self):
        """When imported symbols overlap with changed symbols, severity is WARNING."""
        engine = self._make_engine()
        target = make_test_pr(1, ["src/models.py"])
        target.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="User",
                    symbol_type=SymbolType.CLASS,
                    file_path="src/models.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_signature",
                diff_lines=(1, 10),
            ),
        ]
        other = make_test_pr(2, ["src/views.py"])

        # views.py imports User from src.models — and User changed
        graph = self._make_graph([("src/views.py", "src.models", ["User"])])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        assert result[0].severity == ConflictSeverity.WARNING


class TestBuildChangedSymbols:
    """Tests for _build_changed_symbols three-way classification."""

    def _make_engine(self):
        """Create a minimal engine with mocked symbol index and content cache."""
        engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._content_cache = {}
        engine._cache_lock = threading.Lock()
        engine._symbol_index = MagicMock()
        return engine

    def _make_symbol(self, name, start, end, sig=None, parent=None, file_path="test.py"):
        return Symbol(
            name=name,
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            start_line=start,
            end_line=end,
            signature=sig,
            parent=parent,
        )

    def test_new_function_before_existing_is_added(self):
        """Insert new function before existing → new is 'added', existing is NOT listed."""
        engine = self._make_engine()

        # BASE has one function at lines 10-20
        base_sym = self._make_symbol("existing_func", 10, 20, sig="def existing_func():")
        # HEAD has a new function at lines 10-15 and existing shifted to 20-30
        new_sym = self._make_symbol("new_func", 10, 15, sig="def new_func():")
        existing_head = self._make_symbol("existing_func", 20, 30, sig="def existing_func():")

        engine._symbol_index.get_symbols_and_call_graph.side_effect = [
            ([base_sym], {}),  # BASE call
            ([new_sym, existing_head], {}),  # HEAD call
        ]
        engine._get_file_content_cached = MagicMock(return_value="head content")

        pr = make_test_pr(1, ["test.py"])
        changed_file = pr.changed_files[0]

        # Diff adds lines 10-15 in HEAD (where new_func is)
        file_diff = FileDiff(
            path="test.py",
            old_path=None,
            hunks=[
                DiffHunk(
                    old_start=10,
                    old_count=0,
                    new_start=10,
                    new_count=6,
                    added_lines=[(i, f"    line{i}") for i in range(10, 16)],
                    removed_lines=[],
                    context_lines=[],
                )
            ],
        )
        modified_ranges = [(10, 15)]

        result = engine._build_changed_symbols(
            pr,
            changed_file,
            [file_diff],
            modified_ranges,
            "base content",
        )

        names = {cs.symbol.name for cs in result}
        assert "new_func" in names
        assert "existing_func" not in names

        added = [cs for cs in result if cs.symbol.name == "new_func"]
        assert len(added) == 1
        assert added[0].change_type == "added"

    def test_function_modified_in_place(self):
        """Body change to existing function → 'modified_body'."""
        engine = self._make_engine()

        base_sym = self._make_symbol("func", 10, 20, sig="def func():")
        head_sym = self._make_symbol("func", 10, 20, sig="def func():")

        engine._symbol_index.get_symbols_and_call_graph.side_effect = [
            ([base_sym], {"func": {"helper"}}),
            ([head_sym], {}),
        ]
        engine._get_file_content_cached = MagicMock(return_value="head content")

        pr = make_test_pr(1, ["test.py"])
        changed_file = pr.changed_files[0]

        file_diff = FileDiff(
            path="test.py",
            old_path=None,
            hunks=[
                DiffHunk(
                    old_start=14,
                    old_count=1,
                    new_start=14,
                    new_count=2,
                    added_lines=[(14, "    new_line"), (15, "    another")],
                    removed_lines=[(14, "    old_line")],
                    context_lines=[],
                )
            ],
        )
        modified_ranges = [(14, 15)]

        result = engine._build_changed_symbols(
            pr,
            changed_file,
            [file_diff],
            modified_ranges,
            "base content",
        )

        assert len(result) == 1
        assert result[0].change_type == "modified_body"
        assert result[0].symbol.name == "func"
        # Should carry over call graph from BASE
        assert "helper" in result[0].symbol.dependencies

    def test_function_signature_changed(self):
        """Signature change → 'modified_signature'."""
        engine = self._make_engine()

        base_sym = self._make_symbol("func", 10, 20, sig="def func(a):")
        head_sym = self._make_symbol("func", 10, 20, sig="def func(a, b):")

        engine._symbol_index.get_symbols_and_call_graph.side_effect = [
            ([base_sym], {}),
            ([head_sym], {}),
        ]
        engine._get_file_content_cached = MagicMock(return_value="head content")

        pr = make_test_pr(1, ["test.py"])
        changed_file = pr.changed_files[0]

        file_diff = FileDiff(
            path="test.py",
            old_path=None,
            hunks=[
                DiffHunk(
                    old_start=10,
                    old_count=1,
                    new_start=10,
                    new_count=1,
                    added_lines=[(10, "def func(a, b):")],
                    removed_lines=[(10, "def func(a):")],
                    context_lines=[],
                )
            ],
        )
        modified_ranges = [(10, 10)]

        result = engine._build_changed_symbols(
            pr,
            changed_file,
            [file_diff],
            modified_ranges,
            "base content",
        )

        assert len(result) == 1
        assert result[0].change_type == "modified_signature"
        assert result[0].symbol.name == "func"

    def test_function_removed(self):
        """Deleted function → 'removed'."""
        engine = self._make_engine()

        base_sym = self._make_symbol("old_func", 10, 20, sig="def old_func():")
        # HEAD has no old_func

        engine._symbol_index.get_symbols_and_call_graph.side_effect = [
            ([base_sym], {}),
            ([], {}),
        ]
        engine._get_file_content_cached = MagicMock(return_value="head content")

        pr = make_test_pr(1, ["test.py"])
        changed_file = pr.changed_files[0]

        file_diff = FileDiff(
            path="test.py",
            old_path=None,
            hunks=[
                DiffHunk(
                    old_start=10,
                    old_count=11,
                    new_start=10,
                    new_count=0,
                    added_lines=[],
                    removed_lines=[(i, f"    line{i}") for i in range(10, 21)],
                    context_lines=[],
                )
            ],
        )
        modified_ranges = []  # No added lines

        result = engine._build_changed_symbols(
            pr,
            changed_file,
            [file_diff],
            modified_ranges,
            "base content",
        )

        assert len(result) == 1
        assert result[0].change_type == "removed"
        assert result[0].symbol.name == "old_func"

    def test_displaced_function_not_reported(self):
        """Function shifted down by insertion above → NOT in changed_symbols."""
        engine = self._make_engine()

        # BASE: func_a at 1-5, func_b at 10-20
        base_a = self._make_symbol("func_a", 1, 5, sig="def func_a():")
        base_b = self._make_symbol("func_b", 10, 20, sig="def func_b():")

        # HEAD: func_a at 1-5, new_func at 6-9, func_b at 14-24 (shifted down)
        head_a = self._make_symbol("func_a", 1, 5, sig="def func_a():")
        head_new = self._make_symbol("new_func", 6, 9, sig="def new_func():")
        head_b = self._make_symbol("func_b", 14, 24, sig="def func_b():")

        engine._symbol_index.get_symbols_and_call_graph.side_effect = [
            ([base_a, base_b], {}),
            ([head_a, head_new, head_b], {}),
        ]
        engine._get_file_content_cached = MagicMock(return_value="head content")

        pr = make_test_pr(1, ["test.py"])
        changed_file = pr.changed_files[0]

        # Diff adds lines 6-9 in HEAD (new_func insertion)
        file_diff = FileDiff(
            path="test.py",
            old_path=None,
            hunks=[
                DiffHunk(
                    old_start=6,
                    old_count=0,
                    new_start=6,
                    new_count=4,
                    added_lines=[(i, f"    line{i}") for i in range(6, 10)],
                    removed_lines=[],
                    context_lines=[],
                )
            ],
        )
        modified_ranges = [(6, 9)]

        result = engine._build_changed_symbols(
            pr,
            changed_file,
            [file_diff],
            modified_ranges,
            "base content",
        )

        names = {cs.symbol.name for cs in result}
        # Only the new function should appear
        assert "new_func" in names
        # Displaced functions should NOT appear
        assert "func_a" not in names
        assert "func_b" not in names

    def test_fork_pr_falls_back_gracefully(self):
        """Fork PR (no HEAD) → uses BASE-only logic, does not crash."""
        engine = self._make_engine()

        base_sym = self._make_symbol("func", 10, 20, sig="def func():")

        engine._symbol_index.get_symbols_and_call_graph.return_value = (
            [base_sym],
            {"func": {"helper"}},
        )

        pr = make_test_pr(1, ["test.py"])
        pr.is_fork = True
        changed_file = pr.changed_files[0]

        file_diff = FileDiff(
            path="test.py",
            old_path=None,
            hunks=[
                DiffHunk(
                    old_start=14,
                    old_count=1,
                    new_start=14,
                    new_count=2,
                    added_lines=[(14, "    new_line"), (15, "    another")],
                    removed_lines=[(14, "    old_line")],
                    context_lines=[],
                )
            ],
        )
        modified_ranges = [(14, 15)]

        result = engine._build_changed_symbols(
            pr,
            changed_file,
            [file_diff],
            modified_ranges,
            "base content",
        )

        assert len(result) == 1
        assert result[0].change_type == "modified_body"
        assert result[0].symbol.name == "func"
