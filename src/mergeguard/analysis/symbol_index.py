"""Index of functions/classes/exports per file.

Caches extracted symbols per file per commit SHA to avoid
redundant AST parsing across multiple PR comparisons.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from mergeguard.analysis.ast_parser import extract_symbols, extract_symbols_and_call_graph

if TYPE_CHECKING:
    from mergeguard.models import Symbol


class SymbolIndex:
    """In-memory index of symbols per file, with optional cache key."""

    def __init__(self) -> None:
        # Cache: (file_path, ref) -> list[Symbol]
        self._cache: dict[tuple[str, str], list[Symbol]] = {}
        self._cg_cache: dict[tuple[str, ...], dict[str, set[str]]] = {}
        self._lock = threading.Lock()

    def get_symbols(
        self,
        file_path: str,
        source_code: str,
        ref: str = "HEAD",
    ) -> list[Symbol]:
        """Get symbols for a file, using cache if available.

        Args:
            file_path: The file path for language detection.
            source_code: The full file content.
            ref: Git ref (branch/SHA) used as cache key.

        Returns:
            List of Symbol objects extracted from the file.
        """
        cache_key = (file_path, ref)
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
        symbols = extract_symbols(source_code, file_path)
        with self._lock:
            if cache_key not in self._cache:
                self._cache[cache_key] = symbols
            return self._cache[cache_key]

    def get_symbols_and_call_graph(
        self,
        file_path: str,
        source_code: str,
        ref: str = "HEAD",
    ) -> tuple[list[Symbol], dict[str, set[str]]]:
        """Get symbols and call graph for a file, parsing source only once."""
        cache_key = (file_path, ref)
        call_graph_key = ("cg", file_path, ref)
        with self._lock:
            if cache_key in self._cache and call_graph_key in self._cg_cache:
                return self._cache[cache_key], self._cg_cache[call_graph_key]
        symbols, call_graph = extract_symbols_and_call_graph(source_code, file_path)
        with self._lock:
            self._cache.setdefault(cache_key, symbols)
            self._cg_cache.setdefault(call_graph_key, call_graph)
        return self._cache[cache_key], self._cg_cache[call_graph_key]

    def find_symbol(
        self,
        file_path: str,
        symbol_name: str,
        ref: str = "HEAD",
    ) -> Symbol | None:
        """Find a specific symbol by name in a file.

        Returns None if the file hasn't been indexed or symbol not found.
        """
        cache_key = (file_path, ref)
        symbols = self._cache.get(cache_key, [])
        for sym in symbols:
            if sym.name == symbol_name:
                return sym
        return None

    def find_callers(
        self,
        symbol_name: str,
        ref: str = "HEAD",
    ) -> list[Symbol]:
        """Find all symbols that reference the given symbol name.

        Searches across all indexed files for the given ref.
        """
        callers: list[Symbol] = []
        for (_, cached_ref), symbols in self._cache.items():
            if cached_ref != ref:
                continue
            for sym in symbols:
                if symbol_name in sym.dependencies:
                    callers.append(sym)
        return callers

    def build_cross_file_call_graph(
        self,
        import_graph: object | None = None,
        ref: str = "HEAD",
    ) -> dict[str, dict[str, set[str]]]:
        """Build cross-file call graph after all files are indexed.

        For each function in the cache, resolves calls against symbols
        in imported files (using the import graph to narrow search).

        Returns {file_path: {function_name: {qualified_callee_refs}}}.
        """
        if import_graph is None:
            return {}

        from mergeguard.analysis.dependency import DependencyGraph

        if not isinstance(import_graph, DependencyGraph):
            return {}

        graph: DependencyGraph = import_graph

        # Collect all symbols across all files for this ref
        all_symbols: dict[str, dict[str, str]] = {}  # file -> {symbol_name: qualified_name}
        for (fp, cached_ref), symbols in self._cache.items():
            if cached_ref != ref:
                continue
            for sym in symbols:
                all_symbols.setdefault(fp, {})[sym.name] = f"{fp}:{sym.name}"

        cross_file_cg: dict[str, dict[str, set[str]]] = {}

        for (fp, cached_ref), symbols in self._cache.items():
            if cached_ref != ref:
                continue

            # Get files this file imports
            imported_files = graph._forward.get(fp, set())

            # Get symbol-level imports
            symbol_imports = graph._symbol_forward.get(fp, {})

            for sym in symbols:
                if not sym.dependencies:
                    continue
                resolved: set[str] = set()
                for dep_name in sym.dependencies:
                    # Check if this dependency is in an imported file
                    for imp_file in imported_files:
                        imp_symbols = all_symbols.get(imp_file, {})
                        if dep_name in imp_symbols:
                            resolved.add(imp_symbols[dep_name])
                            break
                    # Also check symbol-level imports for precise matching
                    for imp_file, imported_names in symbol_imports.items():
                        if dep_name in imported_names:
                            file_syms = all_symbols.get(imp_file, {})
                            if dep_name in file_syms:
                                resolved.add(file_syms[dep_name])

                if resolved:
                    cross_file_cg.setdefault(fp, {})[sym.name] = resolved
                    # Update the symbol's dependencies with qualified references
                    sym.dependencies = list(set(sym.dependencies) | {r for r in resolved})

        return cross_file_cg

    def clear(self) -> None:
        """Clear the entire symbol cache."""
        self._cache.clear()

    def clear_file(self, file_path: str, ref: str = "HEAD") -> None:
        """Remove cached symbols for a specific file and ref."""
        self._cache.pop((file_path, ref), None)
