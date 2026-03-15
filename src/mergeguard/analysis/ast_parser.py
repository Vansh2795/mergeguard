"""Tree-sitter based source code parser for extracting symbols."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from tree_sitter_language_pack import get_parser

from mergeguard.models import Symbol, SymbolType

if TYPE_CHECKING:
    from tree_sitter import Node


def _safe_decode(node_text: bytes | None) -> str:
    """Decode tree-sitter node text, replacing invalid bytes."""
    if node_text is None:
        return ""
    return node_text.decode("utf-8", errors="replace")


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
        parser = get_parser(cast("Any", language_name))
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
                child,
                symbols,
                file_path,
                language,
                func_types,
                class_types,
                method_types,
                parent_class=name,
            )
        return

    if node.type in func_types:
        name = _get_name(node)
        if name:
            # If inside a class, it's a method
            sym_type = SymbolType.METHOD if parent_class is not None else SymbolType.FUNCTION
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
                child,
                symbols,
                file_path,
                language,
                func_types,
                class_types,
                method_types,
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
            child,
            symbols,
            file_path,
            language,
            func_types,
            class_types,
            method_types,
            parent_class=parent_class,
        )


# ── Call node types per language ──

CALL_NODE_TYPES: dict[str, str] = {
    "python": "call",
    "javascript": "call_expression",
    "typescript": "call_expression",
    "tsx": "call_expression",
    "go": "call_expression",
    "rust": "call_expression",
    "java": "method_invocation",
    "ruby": "call",
    "c": "call_expression",
    "cpp": "call_expression",
    "c_sharp": "invocation_expression",
}


def extract_call_graph(source_code: str, file_path: str) -> dict[str, set[str]]:
    """Extract intra-file function call relationships.

    Returns {function_name: {names_of_functions_it_calls}}.
    Only includes calls to names that are also defined in the same file.
    """
    language_name = detect_language(file_path)
    if language_name is None:
        return {}

    try:
        parser = get_parser(cast("Any", language_name))
    except Exception:
        return {}

    tree = parser.parse(source_code.encode("utf-8"))
    call_node_type = CALL_NODE_TYPES.get(language_name)
    if call_node_type is None:
        return {}

    func_types = FUNCTION_NODE_TYPES.get(language_name, set())
    class_types = CLASS_NODE_TYPES.get(language_name, set())

    # First pass: collect all defined symbol names
    local_symbols: set[str] = set()
    _collect_defined_names(tree.root_node, local_symbols, func_types, class_types)

    # Second pass: for each function/method, find calls within its body
    call_graph: dict[str, set[str]] = {}
    _collect_calls(
        tree.root_node,
        call_graph,
        local_symbols,
        func_types,
        class_types,
        call_node_type,
        language_name,
    )

    return call_graph


def extract_symbols_and_call_graph(
    source_code: str,
    file_path: str,
) -> tuple[list[Symbol], dict[str, set[str]]]:
    """Parse source once and extract both symbols and call graph."""
    language_name = detect_language(file_path)
    if language_name is None:
        return [], {}

    try:
        parser = get_parser(cast("Any", language_name))
    except Exception:
        return _fallback_extract(source_code, file_path), {}

    tree = parser.parse(source_code.encode("utf-8"))

    # Extract symbols
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

    # Extract call graph (reuses the same parsed tree)
    call_node_type = CALL_NODE_TYPES.get(language_name)
    call_graph: dict[str, set[str]] = {}
    if call_node_type:
        local_symbols: set[str] = set()
        _collect_defined_names(tree.root_node, local_symbols, func_types, class_types)
        _collect_calls(
            tree.root_node,
            call_graph,
            local_symbols,
            func_types,
            class_types,
            call_node_type,
            language_name,
        )

    return symbols, call_graph


def _collect_defined_names(
    node: Node,
    names: set[str],
    func_types: set[str],
    class_types: set[str],
) -> None:
    """Recursively collect all defined function/method/class names."""
    if node.type in func_types or node.type in class_types:
        name = _get_name(node)
        if name:
            names.add(name)
    for child in node.children:
        _collect_defined_names(child, names, func_types, class_types)


def _collect_calls(
    node: Node,
    call_graph: dict[str, set[str]],
    local_symbols: set[str],
    func_types: set[str],
    class_types: set[str],
    call_node_type: str,
    language: str,
    current_func: str | None = None,
) -> None:
    """Recursively walk tree, tracking which function we're inside."""
    if node.type in func_types:
        name = _get_name(node)
        if name:
            # Enter this function scope
            call_graph.setdefault(name, set())
            for child in node.children:
                _collect_calls(
                    child,
                    call_graph,
                    local_symbols,
                    func_types,
                    class_types,
                    call_node_type,
                    language,
                    current_func=name,
                )
            return

    if node.type in class_types:
        # Recurse into class body but don't set current_func
        for child in node.children:
            _collect_calls(
                child,
                call_graph,
                local_symbols,
                func_types,
                class_types,
                call_node_type,
                language,
                current_func=current_func,
            )
        return

    if node.type == call_node_type and current_func is not None:
        callee = _extract_callee_name(node, language)
        if callee and callee in local_symbols and callee != current_func:
            call_graph[current_func].add(callee)

    for child in node.children:
        _collect_calls(
            child,
            call_graph,
            local_symbols,
            func_types,
            class_types,
            call_node_type,
            language,
            current_func=current_func,
        )


def _extract_callee_name(call_node: Node, language: str) -> str | None:
    """Resolve a call AST node to a function name string."""
    if language == "python":
        # Python call: child is either identifier (direct) or attribute (method)
        for child in call_node.children:
            if child.type == "identifier":
                return _safe_decode(child.text)
            if child.type == "attribute":
                # self.method() → extract the attribute name (last identifier)
                for attr_child in child.children:
                    if attr_child.type == "identifier" and attr_child != child.children[0]:
                        return _safe_decode(attr_child.text)
        return None

    if language in ("javascript", "typescript", "tsx"):
        for child in call_node.children:
            if child.type == "identifier":
                return _safe_decode(child.text)
            if child.type == "member_expression":
                for mc in child.children:
                    if mc.type == "property_identifier":
                        return _safe_decode(mc.text)
        return None

    if language == "go":
        for child in call_node.children:
            if child.type == "identifier":
                return _safe_decode(child.text)
            if child.type == "selector_expression":
                for sc in child.children:
                    if sc.type == "field_identifier":
                        return _safe_decode(sc.text)
        return None

    if language == "java":
        for child in call_node.children:
            if child.type == "identifier":
                return _safe_decode(child.text)
        return None

    if language == "rust":
        for child in call_node.children:
            if child.type == "identifier":
                return _safe_decode(child.text)
            if child.type == "field_expression":
                for fc in child.children:
                    if fc.type == "field_identifier":
                        return _safe_decode(fc.text)
        return None

    # Fallback: look for any identifier child
    for child in call_node.children:
        if child.type == "identifier":
            return _safe_decode(child.text)
    return None


# ── Cyclomatic complexity ──

_BRANCH_NODE_TYPES: dict[str, set[str]] = {
    "python": {"if_statement", "for_statement", "while_statement", "except_clause",
               "boolean_operator", "conditional_expression"},
    "javascript": {"if_statement", "for_statement", "while_statement", "for_in_statement",
                    "catch_clause", "ternary_expression", "switch_case"},
    "typescript": {"if_statement", "for_statement", "while_statement", "for_in_statement",
                    "catch_clause", "ternary_expression", "switch_case"},
    "tsx": {"if_statement", "for_statement", "while_statement", "for_in_statement",
            "catch_clause", "ternary_expression", "switch_case"},
    "go": {"if_statement", "for_statement", "select_statement", "type_switch_statement",
           "communication_case", "expression_case"},
    "rust": {"if_expression", "for_expression", "while_expression", "match_arm",
             "closure_expression"},
    "java": {"if_statement", "for_statement", "while_statement", "catch_clause",
             "ternary_expression", "switch_expression"},
    "c": {"if_statement", "for_statement", "while_statement", "case_statement",
          "conditional_expression"},
    "cpp": {"if_statement", "for_statement", "while_statement", "catch_clause",
            "case_statement", "conditional_expression"},
    "c_sharp": {"if_statement", "for_statement", "while_statement", "catch_clause",
                "case_switch_label", "conditional_expression"},
}


def _count_branches(node: Node, branch_types: set[str]) -> int:
    """Recursively count branching nodes in an AST subtree."""
    count = 1 if node.type in branch_types else 0
    for child in node.children:
        count += _count_branches(child, branch_types)
    return count


def compute_cyclomatic_complexity(source_code: str, file_path: str) -> int:
    """Compute approximate cyclomatic complexity for a code snippet.

    Counts branching nodes (if/for/while/and/or/except/case) + 1.
    Works on partial source (e.g., diff hunks) by parsing what's available.
    """
    language_name = detect_language(file_path)
    if language_name is None:
        return 1

    try:
        parser = get_parser(cast("Any", language_name))
    except Exception:
        return 1

    tree = parser.parse(source_code.encode("utf-8"))
    branch_types = _BRANCH_NODE_TYPES.get(language_name, set())
    if not branch_types:
        return 1

    return 1 + _count_branches(tree.root_node, branch_types)


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
            return _safe_decode(child.text)
    return None


def _extract_signature(node: Node) -> str | None:
    """Extract the function/method signature (first line)."""
    text = _safe_decode(node.text)
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
