"""Import graph builder for cross-file dependency analysis.

Builds a directed graph of file-level imports to compute
blast radius and detect transitive conflicts.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ImportEdge:
    """A single import relationship from one file to another."""

    source_file: str  # The file doing the importing
    target_file: str  # The file being imported
    imported_names: list[str] = field(default_factory=list)  # Specific symbols imported


@dataclass
class DependencyGraph:
    """Directed graph of file-level import relationships."""

    edges: list[ImportEdge] = field(default_factory=list)
    # Adjacency list: file -> files it imports
    _forward: dict[str, set[str]] = field(default_factory=dict)
    # Reverse adjacency: file -> files that import it
    _reverse: dict[str, set[str]] = field(default_factory=dict)
    # Symbol-level forward: file -> {target_file: {symbol_names}}
    _symbol_forward: dict[str, dict[str, set[str]]] = field(default_factory=dict)

    def add_edge(self, edge: ImportEdge) -> None:
        """Add an import edge to the graph."""
        self.edges.append(edge)
        self._forward.setdefault(edge.source_file, set()).add(edge.target_file)
        self._reverse.setdefault(edge.target_file, set()).add(edge.source_file)
        # Build symbol-level index
        if edge.imported_names:
            self._symbol_forward.setdefault(edge.source_file, {}).setdefault(
                edge.target_file, set()
            ).update(edge.imported_names)

    def get_files_importing_symbol(self, target_file: str, symbol_name: str) -> set[str]:
        """Find all files that import a specific symbol from target_file.

        Checks both direct file paths and module-form paths.
        """
        importers: set[str] = set()
        for source_file, targets in self._symbol_forward.items():
            for target, names in targets.items():
                if target == target_file and symbol_name in names:
                    importers.add(source_file)
        return importers

    def get_all_importers_of_file(self, target_file: str) -> dict[str, set[str]]:
        """Get all files that import from target_file, with their imported symbol names.

        Returns {importing_file: {symbol_names}}.
        """
        result: dict[str, set[str]] = {}
        for source_file, targets in self._symbol_forward.items():
            if target_file in targets:
                result[source_file] = targets[target_file]
        return result

    def get_direct_imports(self, file_path: str) -> set[str]:
        """Get files directly imported by the given file."""
        return self._forward.get(file_path, set())

    def get_symbol_imports(self, file_path: str) -> dict[str, set[str]]:
        """Get symbol-level imports for the given file.

        Returns {target_file: {symbol_names}}.
        """
        return self._symbol_forward.get(file_path, {})

    def get_dependents(self, file_path: str, max_depth: int = 5) -> set[str]:
        """Find all files that transitively depend on the given file.

        Uses BFS to find all reverse-transitive dependencies up to max_depth.
        """
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(file_path, 0)])

        while queue:
            current, depth = queue.popleft()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            for dep in self._reverse.get(current, set()):
                queue.append((dep, depth + 1))

        visited.discard(file_path)  # Don't include the file itself
        return visited

    def get_dependencies(self, file_path: str, max_depth: int = 5) -> set[str]:
        """Find all files that the given file transitively depends on."""
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(file_path, 0)])

        while queue:
            current, depth = queue.popleft()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            for dep in self._forward.get(current, set()):
                queue.append((dep, depth + 1))

        visited.discard(file_path)
        return visited

    def get_imported_names(self, source_file: str, target_file: str) -> list[str]:
        """Get specific names that source_file imports from target_file."""
        for edge in self.edges:
            if edge.source_file == source_file and edge.target_file == target_file:
                return edge.imported_names
        return []

    def dependency_depth(self, file_path: str) -> int:
        """Compute the longest reverse-dependency chain depth.

        Returns the longest chain length (e.g., A imports B imports C imports
        target → depth 3), not the total number of dependents.
        """
        max_depth = 0
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(file_path, 0)])
        while queue:
            current, depth = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            max_depth = max(max_depth, depth)
            for dep in self._reverse.get(current, set()):
                if dep not in visited:
                    queue.append((dep, depth + 1))
                elif dep == file_path:
                    logger.debug(
                        "Circular dependency detected: %s ↔ %s",
                        file_path,
                        current,
                    )
        return max_depth


# ── Import extraction patterns ──

PYTHON_FROM_IMPORT = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+(.+?)(?:\s*#.*)?$", re.MULTILINE)
PYTHON_IMPORT_MODULE = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)

JS_IMPORT = re.compile(
    r"""(?:import\s+.*?\s+from\s+['"](.+?)['"]|require\s*\(\s*['"](.+?)['"]\s*\))""",
    re.MULTILINE,
)
JS_NAMED_IMPORT = re.compile(r"""import\s+\{([^}]+)\}\s+from\s+['"](.+?)['"]""", re.MULTILINE)

GO_IMPORT_BLOCK = re.compile(r"import\s*\(\s*((?:[^)]*\n?)*?)\s*\)", re.MULTILINE)
GO_IMPORT_SINGLE = re.compile(r'import\s+"([\w./-]+)"')
GO_IMPORT_PATH = re.compile(r'"([\w./-]+)"')


def extract_imports(source_code: str, file_path: str) -> list[str]:
    """Extract import targets from source code.

    Returns a list of module/file references that this file imports.
    Language is detected from the file extension.
    """
    if file_path.endswith(".py"):
        return [mod for mod, _names in _extract_python_imports(source_code)]
    elif file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
        return [mod for mod, _names in _extract_js_imports(source_code)]
    elif file_path.endswith(".go"):
        return _extract_go_imports(source_code)
    return []


def extract_imports_with_names(
    source_code: str,
    file_path: str,
) -> list[tuple[str, list[str]]]:
    """Extract import targets with specific imported names.

    Returns list of (module, imported_names) tuples.
    """
    if file_path.endswith(".py"):
        return _extract_python_imports(source_code)
    elif file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
        return _extract_js_imports(source_code)
    elif file_path.endswith(".go"):
        return [(mod, []) for mod in _extract_go_imports(source_code)]
    return []


def _parse_import_names(names_str: str) -> list[str]:
    """Parse comma-separated import names, handling aliases and whitespace."""
    names: list[str] = []
    for name in names_str.split(","):
        name = name.strip().rstrip(")")
        if not name or name.startswith("#"):
            continue
        if " as " in name:
            name = name.split(" as ")[0].strip()
        if name:
            names.append(name)
    return names


def _extract_python_imports(source_code: str) -> list[tuple[str, list[str]]]:
    """Extract Python imports with specific imported names.

    Returns list of (module, imported_names) tuples.
    - ``from X import Y, Z`` → ("X", ["Y", "Z"])
    - ``from X import (\\n    Y,\\n    Z)`` → ("X", ["Y", "Z"])
    - ``import X`` → ("X", [])
    """
    imports: list[tuple[str, list[str]]] = []
    seen_from_modules: set[str] = set()

    for match in PYTHON_FROM_IMPORT.finditer(source_code):
        module = match.group(1)
        names_str = match.group(2).strip()
        if names_str.startswith("("):
            # Multi-line import: find closing paren in source
            start_pos = match.end()
            paren_content = names_str[1:]  # skip opening paren
            close_idx = source_code.find(")", start_pos)
            if close_idx != -1:
                paren_content = names_str[1:] + source_code[start_pos:close_idx]
            names = _parse_import_names(paren_content)
            imports.append((module, names))
        else:
            names = _parse_import_names(names_str)
            imports.append((module, names))
        seen_from_modules.add(module)

    for match in PYTHON_IMPORT_MODULE.finditer(source_code):
        module = match.group(1)
        if module not in seen_from_modules:
            imports.append((module, []))

    return imports


def _extract_js_imports(source_code: str) -> list[tuple[str, list[str]]]:
    """Extract JavaScript/TypeScript imports with specific imported names.

    Returns list of (module, imported_names) tuples.
    - ``import { Y, Z } from 'X'`` → ("X", ["Y", "Z"])
    - ``import X from 'X'`` → ("X", [])
    """
    imports: list[tuple[str, list[str]]] = []
    seen_modules: set[str] = set()

    # First pass: named imports with specific symbols
    for match in JS_NAMED_IMPORT.finditer(source_code):
        names_str = match.group(1)
        module = match.group(2)
        names = []
        for name in names_str.split(","):
            name = name.strip()
            if not name:
                continue
            if " as " in name:
                name = name.split(" as ")[0].strip()
            names.append(name)
        imports.append((module, names))
        seen_modules.add(module)

    # Second pass: other imports (default, require, etc.)
    for match in JS_IMPORT.finditer(source_code):
        module = match.group(1) or match.group(2)
        if module and module not in seen_modules:
            imports.append((module, []))
            seen_modules.add(module)

    return imports


def build_dependency_graph(
    file_contents: list[tuple[str, str]],
) -> DependencyGraph:
    """Build a DependencyGraph from a list of (file_path, source_code) tuples.

    For each file, extracts import targets and creates ImportEdge objects
    mapping the source file to each imported module/file.
    """
    graph = DependencyGraph()
    for file_path, source_code in file_contents:
        imported_modules = extract_imports_with_names(source_code, file_path)
        for target, names in imported_modules:
            edge = ImportEdge(
                source_file=file_path,
                target_file=target,
                imported_names=names,
            )
            graph.add_edge(edge)
    return graph


def _extract_go_imports(source_code: str) -> list[str]:
    """Extract Go import targets, scoped to import statements only."""
    imports: list[str] = []
    # Match import blocks: import ( ... )
    for match in GO_IMPORT_BLOCK.finditer(source_code):
        block = match.group(1)
        for path_match in GO_IMPORT_PATH.finditer(block):
            imports.append(path_match.group(1))
    # Match single imports: import "pkg"
    for match in GO_IMPORT_SINGLE.finditer(source_code):
        path = match.group(1)
        if path not in imports:
            imports.append(path)
    return imports
