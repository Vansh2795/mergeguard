"""Tests for ast_parser module."""

from __future__ import annotations

from mergeguard.analysis.ast_parser import detect_language, extract_symbols, map_diff_to_symbols
from mergeguard.models import Symbol, SymbolType


class TestDetectLanguage:
    def test_python_detection(self):
        assert detect_language("main.py") == "python"

    def test_typescript_detection(self):
        assert detect_language("app.tsx") == "tsx"

    def test_javascript_detection(self):
        assert detect_language("index.js") == "javascript"

    def test_go_detection(self):
        assert detect_language("main.go") == "go"

    def test_unknown_extension(self):
        assert detect_language("file.xyz") is None


class TestExtractSymbols:
    def test_extract_python_functions(self):
        source = "def hello():\n    pass\n\ndef world():\n    pass\n"
        symbols = extract_symbols(source, "test.py")
        names = {s.name for s in symbols}
        assert "hello" in names
        assert "world" in names

    def test_extract_python_classes(self):
        source = "class MyClass:\n    def method(self):\n        pass\n"
        symbols = extract_symbols(source, "test.py")
        assert any(s.name == "MyClass" for s in symbols)

    def test_extract_python_methods(self):
        source = "class Foo:\n    def bar(self):\n        pass\n    def baz(self):\n        pass\n"
        symbols = extract_symbols(source, "test.py")
        method_names = {s.name for s in symbols if s.symbol_type == SymbolType.METHOD}
        assert "bar" in method_names
        assert "baz" in method_names

    def test_symbol_line_ranges(self):
        source = "def first():\n    pass\n\n\ndef second():\n    x = 1\n    return x\n"
        symbols = extract_symbols(source, "test.py")
        first = next(s for s in symbols if s.name == "first")
        assert first.start_line == 1
        assert first.end_line >= 2

    def test_fallback_for_unknown_language(self):
        symbols = extract_symbols("", "file.xyz")
        assert symbols == []

    def test_fallback_regex_extraction(self):
        from mergeguard.analysis.ast_parser import _fallback_extract
        source = "def some_func():\n    pass\nclass SomeClass:\n    pass\n"
        symbols = _fallback_extract(source, "test.unknown")
        names = {s.name for s in symbols}
        assert "some_func" in names
        assert "SomeClass" in names


class TestMapDiffToSymbols:
    def test_symbol_overlap_detection(self):
        symbols = [
            Symbol(name="func_a", symbol_type=SymbolType.FUNCTION, file_path="f.py", start_line=10, end_line=20),
            Symbol(name="func_b", symbol_type=SymbolType.FUNCTION, file_path="f.py", start_line=25, end_line=35),
        ]
        affected = map_diff_to_symbols(symbols, [(15, 18)])
        assert len(affected) == 1
        assert affected[0].name == "func_a"

    def test_no_overlap(self):
        symbols = [
            Symbol(name="func_a", symbol_type=SymbolType.FUNCTION, file_path="f.py", start_line=10, end_line=20),
        ]
        affected = map_diff_to_symbols(symbols, [(25, 30)])
        assert len(affected) == 0

    def test_multiple_symbols_affected(self):
        symbols = [
            Symbol(name="func_a", symbol_type=SymbolType.FUNCTION, file_path="f.py", start_line=10, end_line=20),
            Symbol(name="func_b", symbol_type=SymbolType.FUNCTION, file_path="f.py", start_line=18, end_line=30),
        ]
        affected = map_diff_to_symbols(symbols, [(19, 19)])
        assert len(affected) == 2

    def test_boundary_overlap(self):
        symbols = [
            Symbol(name="func_a", symbol_type=SymbolType.FUNCTION, file_path="f.py", start_line=10, end_line=20),
        ]
        # Diff touches exactly the last line of the symbol
        affected = map_diff_to_symbols(symbols, [(20, 20)])
        assert len(affected) == 1
