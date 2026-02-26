"""Index of functions/classes/exports per file.

Caches extracted symbols per file per commit SHA to avoid
redundant AST parsing across multiple PR comparisons.
"""

from __future__ import annotations

from mergeguard.analysis.ast_parser import extract_symbols
from mergeguard.models import Symbol


class SymbolIndex:
    """In-memory index of symbols per file, with optional cache key."""

    def __init__(self) -> None:
        # Cache: (file_path, ref) -> list[Symbol]
        self._cache: dict[tuple[str, str], list[Symbol]] = {}

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
        if cache_key in self._cache:
            return self._cache[cache_key]

        symbols = extract_symbols(source_code, file_path)
        self._cache[cache_key] = symbols
        return symbols

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

    def clear(self) -> None:
        """Clear the entire symbol cache."""
        self._cache.clear()

    def clear_file(self, file_path: str, ref: str = "HEAD") -> None:
        """Remove cached symbols for a specific file and ref."""
        self._cache.pop((file_path, ref), None)
