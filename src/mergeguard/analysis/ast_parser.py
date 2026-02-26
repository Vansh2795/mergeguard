"""Tree-sitter based source code parser for extracting symbols."""

from __future__ import annotations

import re

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from mergeguard.models import Symbol, SymbolType


# ── Language detection ──

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "c_sharp",
    ".swift": "swift",
    ".kt": "kotlin",
}

# ── Node types that represent symbol definitions per language ──

FUNCTION_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition"},
    "javascript": {"function_declaration"},
    "typescript": {"function_declaration"},
    "tsx": {"function_declaration"},
    "go": {"function_declaration"},
    "rust": {"function_item"},
    "java": {"method_declaration"},
    "ruby": {"method"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
    "c_sharp": {"method_declaration"},
}

CLASS_NODE_TYPES: dict[str, set[str]] = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration"},
    "tsx": {"class_declaration"},
    "go": set(),  # Go uses type_declaration
    "rust": {"struct_item", "enum_item", "trait_item"},
    "java": {"class_declaration", "interface_declaration"},
    "c_sharp": {"class_declaration", "interface_declaration"},
}

METHOD_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition"},  # methods are function_definitions inside classes
    "javascript": {"method_definition"},
    "typescript": {"method_definition"},
    "tsx": {"method_definition"},
    "go": {"method_declaration"},
    "java": {"method_declaration"},
    "c_sharp": {"method_declaration"},
}

# Name child node types per language
NAME_NODE_TYPES = {
    "identifier",
    "type_identifier",
    "property_identifier",
    "field_identifier",
    "name",
}


def detect_language(file_path: str) -> str | None:
    """Detect language from file extension."""
    for ext, lang in EXTENSION_TO_LANGUAGE.items():
        if file_path.endswith(ext):
            return lang
    return None


def extract_symbols(source_code: str, file_path: str) -> list[Symbol]:
    """Parse source code and extract all named symbols with their line ranges.

    Uses Tree-sitter for robust, multi-language AST parsing. Falls back
    gracefully if the language isn't supported.

    Args:
        source_code: The full file content
        file_path: File path (used for language detection and symbol metadata)

    Returns:
        List of Symbol objects with accurate line ranges
    """
    language_name = detect_language(file_path)
    if language_name is None:
        return []

    try:
        parser = get_parser(language_name)
    except Exception:
        return _fallback_extract(source_code, file_path)

    tree = parser.parse(source_code.encode("utf-8"))
    symbols: list[Symbol] = []

    func_types = FUNCTION_NODE_TYPES.get(language_name, set())
    class_types = CLASS_NODE_TYPES.get(language_name, set())
    method_types = METHOD_NODE_TYPES.get(language_name, set())

    _walk_tree(
        tree.root_node,
        symbols,
        file_path,
        language_name,
        func_types,
        class_types,
        method_types,
        parent_class=None,
    )

    return symbols


def _walk_tree(
    node: Node,
    symbols: list[Symbol],
    file_path: str,
    language: str,
    func_types: set[str],
    class_types: set[str],
    method_types: set[str],
    parent_class: str | None,
) -> None:
    """Recursively walk the AST and collect symbol definitions."""
    if node.type in class_types:
        name = _get_name(node)
        if name:
            symbols.append(
                Symbol(
                    name=name,
                    symbol_type=SymbolType.CLASS,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=_extract_signature(node),
                )
            )
        # Recurse into class body with this class as parent
        for child in node.children:
            _walk_tree(
                child, symbols, file_path, language,
                func_types, class_types, method_types,
                parent_class=name,
            )
        return

    if node.type in func_types:
        name = _get_name(node)
        if name:
            # If inside a class, it's a method
            if parent_class is not None:
                sym_type = SymbolType.METHOD
            else:
                sym_type = SymbolType.FUNCTION
            symbols.append(
                Symbol(
                    name=name,
                    symbol_type=sym_type,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=_extract_signature(node),
                    parent=parent_class,
                )
            )
        # Still recurse for nested functions/classes
        for child in node.children:
            _walk_tree(
                child, symbols, file_path, language,
                func_types, class_types, method_types,
                parent_class=parent_class,
            )
        return

    # For Go method_declaration (separate from function_declaration)
    if language == "go" and node.type == "method_declaration":
        name = _get_name(node)
        if name:
            symbols.append(
                Symbol(
                    name=name,
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=_extract_signature(node),
                )
            )

    # For Go type declarations
    if language == "go" and node.type == "type_declaration":
        for child in node.children:
            if child.type == "type_spec":
                name = _get_name(child)
                if name:
                    symbols.append(
                        Symbol(
                            name=name,
                            symbol_type=SymbolType.TYPE_ALIAS,
                            file_path=file_path,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=_extract_signature(node),
                        )
                    )

    # Recurse into children
    for child in node.children:
        _walk_tree(
            child, symbols, file_path, language,
            func_types, class_types, method_types,
            parent_class=parent_class,
        )


def map_diff_to_symbols(
    symbols: list[Symbol],
    modified_ranges: list[tuple[int, int]],
) -> list[Symbol]:
    """Given a list of symbols and modified line ranges, return which symbols
    overlap with the modified ranges.

    This is the critical mapping step: "lines 45-67 were changed" →
    "the getUserById function was modified".
    """
    affected: list[Symbol] = []
    for symbol in symbols:
        for mod_start, mod_end in modified_ranges:
            if symbol.start_line <= mod_end and mod_start <= symbol.end_line:
                affected.append(symbol)
                break  # Don't double-count
    return affected


# ── Private helpers ──


def _get_name(node: Node) -> str | None:
    """Extract the name from a definition node by looking at children."""
    for child in node.children:
        if child.type in NAME_NODE_TYPES:
            return child.text.decode("utf-8")
    return None


def _extract_signature(node: Node) -> str | None:
    """Extract the function/method signature (first line)."""
    text = node.text.decode("utf-8")
    first_line = text.split("\n")[0].strip()
    return first_line[:200] if len(first_line) > 200 else first_line


def _fallback_extract(source_code: str, file_path: str) -> list[Symbol]:
    """Basic regex-based symbol extraction for unsupported languages."""
    symbols: list[Symbol] = []
    lines = source_code.split("\n")

    func_pattern = re.compile(
        r"^\s*(?:def|func|function|fn|pub\s+fn|async\s+def|async\s+function)\s+(\w+)"
    )
    class_pattern = re.compile(r"^\s*(?:class|struct|interface|enum|trait)\s+(\w+)")

    for i, line in enumerate(lines):
        func_match = func_pattern.match(line)
        if func_match:
            symbols.append(
                Symbol(
                    name=func_match.group(1),
                    symbol_type=SymbolType.FUNCTION,
                    file_path=file_path,
                    start_line=i + 1,
                    end_line=i + 1,
                    signature=line.strip()[:200],
                )
            )

        class_match = class_pattern.match(line)
        if class_match:
            symbols.append(
                Symbol(
                    name=class_match.group(1),
                    symbol_type=SymbolType.CLASS,
                    file_path=file_path,
                    start_line=i + 1,
                    end_line=i + 1,
                    signature=line.strip()[:200],
                )
            )

    return symbols
