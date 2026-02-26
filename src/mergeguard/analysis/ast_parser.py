"""Tree-sitter based source code parser for extracting symbols."""

from __future__ import annotations

from tree_sitter import Node
from tree_sitter_language_pack import get_language, get_parser

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

# ── Tree-sitter query patterns per language ──
# These define which AST node types represent function/class definitions.

SYMBOL_QUERIES: dict[str, dict[str, str]] = {
    "python": {
        "functions": "(function_definition name: (identifier) @name) @func",
        "classes": "(class_definition name: (identifier) @name) @cls",
        "methods": """
            (class_definition
              body: (block
                (function_definition name: (identifier) @name) @method))
        """,
    },
    "typescript": {
        "functions": """[
            (function_declaration name: (identifier) @name) @func
            (lexical_declaration
              (variable_declarator
                name: (identifier) @name
                value: (arrow_function)) @func)
        ]""",
        "classes": "(class_declaration name: (type_identifier) @name) @cls",
        "methods": """
            (class_declaration
              body: (class_body
                (method_definition name: (property_identifier) @name) @method))
        """,
        "exports": "(export_statement) @export",
    },
    "javascript": {
        "functions": """[
            (function_declaration name: (identifier) @name) @func
            (lexical_declaration
              (variable_declarator
                name: (identifier) @name
                value: (arrow_function)) @func)
        ]""",
        "classes": "(class_declaration name: (identifier) @name) @cls",
        "methods": """
            (class_declaration
              body: (class_body
                (method_definition name: (property_identifier) @name) @method))
        """,
    },
    "go": {
        "functions": "(function_declaration name: (identifier) @name) @func",
        "methods": "(method_declaration name: (field_identifier) @name) @method",
        "types": "(type_declaration (type_spec name: (type_identifier) @name)) @type",
    },
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

    queries = SYMBOL_QUERIES.get(language_name)
    if queries is None:
        # Language supported by tree-sitter but we don't have query patterns yet.
        # Fall back to basic line-based heuristic.
        return _fallback_extract(source_code, file_path)

    parser = get_parser(language_name)
    tree = parser.parse(source_code.encode("utf-8"))
    language = get_language(language_name)

    symbols: list[Symbol] = []

    for symbol_type_key, query_str in queries.items():
        try:
            query = language.query(query_str)
            captures = query.captures(tree.root_node)
        except Exception:
            continue  # Query syntax error for this language version

        # Process captures — they come in pairs: @name and @func/@cls/@method
        i = 0
        while i < len(captures):
            node, capture_name = captures[i]

            if capture_name in ("func", "cls", "method", "type", "export"):
                # This is the full definition node
                name_node = _find_name_child(node, captures, i)
                name = name_node.text.decode("utf-8") if name_node else "<anonymous>"

                sym_type = _map_symbol_type(symbol_type_key)
                signature = _extract_signature(node, language_name)

                # Determine parent (class name for methods)
                parent = _find_parent_class(node) if sym_type == SymbolType.METHOD else None

                symbols.append(
                    Symbol(
                        name=name,
                        symbol_type=sym_type,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1,  # 1-indexed
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                        parent=parent,
                    )
                )

            i += 1

    return symbols


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


def _find_name_child(node: Node, captures: list, current_idx: int) -> Node | None:
    """Find the @name capture that corresponds to this definition."""
    # Look at the next capture — if it's @name, use it
    if current_idx + 1 < len(captures):
        next_node, next_name = captures[current_idx + 1]
        if next_name == "name":
            return next_node
    # Fallback: search children
    for child in node.children:
        if child.type in (
            "identifier",
            "type_identifier",
            "property_identifier",
            "field_identifier",
        ):
            return child
    return None


def _map_symbol_type(key: str) -> SymbolType:
    mapping = {
        "functions": SymbolType.FUNCTION,
        "classes": SymbolType.CLASS,
        "methods": SymbolType.METHOD,
        "types": SymbolType.TYPE_ALIAS,
        "exports": SymbolType.EXPORT,
    }
    return mapping.get(key, SymbolType.FUNCTION)


def _extract_signature(node: Node, language: str) -> str | None:
    """Extract the function/method signature (first line)."""
    text = node.text.decode("utf-8")
    first_line = text.split("\n")[0].strip()
    # Truncate very long signatures
    return first_line[:200] if len(first_line) > 200 else first_line


def _find_parent_class(node: Node) -> str | None:
    """Walk up the AST to find the enclosing class name."""
    current = node.parent
    while current:
        if current.type in ("class_definition", "class_declaration"):
            for child in current.children:
                if child.type in ("identifier", "type_identifier"):
                    return child.text.decode("utf-8")
        current = current.parent
    return None


def _fallback_extract(source_code: str, file_path: str) -> list[Symbol]:
    """Basic regex-based symbol extraction for unsupported languages."""
    # This is intentionally simple — better to have approximate data
    # than no data for unsupported languages.
    import re

    symbols: list[Symbol] = []
    lines = source_code.split("\n")

    # Common function patterns across languages
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
                    end_line=i + 1,  # Unknown end; will be approximate
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
