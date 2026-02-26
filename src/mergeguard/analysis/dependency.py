"""Import graph builder for cross-file dependency analysis.

Builds a directed graph of file-level imports to compute
blast radius and detect transitive conflicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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

    def add_edge(self, edge: ImportEdge) -> None:
        """Add an import edge to the graph."""
        self.edges.append(edge)
        self._forward.setdefault(edge.source_file, set()).add(edge.target_file)
        self._reverse.setdefault(edge.target_file, set()).add(edge.source_file)

    def get_dependents(self, file_path: str, max_depth: int = 5) -> set[str]:
        """Find all files that transitively depend on the given file.

        Uses BFS to find all reverse-transitive dependencies up to max_depth.
        """
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(file_path, 0)]

        while queue:
            current, depth = queue.pop(0)
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
        queue: list[tuple[str, int]] = [(file_path, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            for dep in self._forward.get(current, set()):
                queue.append((dep, depth + 1))

        visited.discard(file_path)
        return visited

    def dependency_depth(self, file_path: str) -> int:
        """Compute how deep in the dependency graph this file sits.

        Returns the length of the longest reverse-dependency chain.
        """
        dependents = self.get_dependents(file_path)
        return len(dependents)


# ── Import extraction patterns ──

PYTHON_IMPORT = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)
JS_IMPORT = re.compile(
    r"""(?:import\s+.*?\s+from\s+['"](.+?)['"]|require\s*\(\s*['"](.+?)['"]\s*\))""",
    re.MULTILINE,
)
GO_IMPORT = re.compile(r'"([\w./]+)"')


def extract_imports(source_code: str, file_path: str) -> list[str]:
    """Extract import targets from source code.

    Returns a list of module/file references that this file imports.
    Language is detected from the file extension.
    """
    if file_path.endswith(".py"):
        return _extract_python_imports(source_code)
    elif file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
        return _extract_js_imports(source_code)
    elif file_path.endswith(".go"):
        return _extract_go_imports(source_code)
    return []


def _extract_python_imports(source_code: str) -> list[str]:
    """Extract Python import targets."""
    imports: list[str] = []
    for match in PYTHON_IMPORT.finditer(source_code):
        module = match.group(1) or match.group(2)
        if module:
            imports.append(module)
    return imports


def _extract_js_imports(source_code: str) -> list[str]:
    """Extract JavaScript/TypeScript import targets."""
    imports: list[str] = []
    for match in JS_IMPORT.finditer(source_code):
        module = match.group(1) or match.group(2)
        if module:
            imports.append(module)
    return imports


def _extract_go_imports(source_code: str) -> list[str]:
    """Extract Go import targets."""
    imports: list[str] = []
    for match in GO_IMPORT.finditer(source_code):
        imports.append(match.group(1))
    return imports
