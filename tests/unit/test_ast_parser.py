"""Tests for ast_parser module."""
from __future__ import annotations
import pytest


class TestDetectLanguage:
    @pytest.mark.skip(reason="Requires tree-sitter-language-pack")
    def test_python_detection(self):
        from mergeguard.analysis.ast_parser import detect_language
        assert detect_language("main.py") == "python"

    @pytest.mark.skip(reason="Requires tree-sitter-language-pack")
    def test_typescript_detection(self):
        from mergeguard.analysis.ast_parser import detect_language
        assert detect_language("app.tsx") == "tsx"

    @pytest.mark.skip(reason="Requires tree-sitter-language-pack")
    def test_unknown_extension(self):
        from mergeguard.analysis.ast_parser import detect_language
        assert detect_language("file.xyz") is None


class TestExtractSymbols:
    @pytest.mark.skip(reason="Requires tree-sitter-language-pack")
    def test_extract_python_functions(self):
        from mergeguard.analysis.ast_parser import extract_symbols
        source = "def hello():\n    pass\n\ndef world():\n    pass\n"
        symbols = extract_symbols(source, "test.py")
        assert len(symbols) >= 2

    @pytest.mark.skip(reason="Requires tree-sitter-language-pack")
    def test_extract_python_classes(self):
        from mergeguard.analysis.ast_parser import extract_symbols
        source = "class MyClass:\n    def method(self):\n        pass\n"
        symbols = extract_symbols(source, "test.py")
        assert any(s.name == "MyClass" for s in symbols)

    @pytest.mark.skip(reason="Requires tree-sitter-language-pack")
    def test_fallback_for_unknown_language(self):
        from mergeguard.analysis.ast_parser import extract_symbols
        symbols = extract_symbols("", "file.xyz")
        assert symbols == []


class TestMapDiffToSymbols:
    @pytest.mark.skip(reason="Requires tree-sitter-language-pack")
    def test_symbol_overlap_detection(self):
        from mergeguard.analysis.ast_parser import map_diff_to_symbols
        from mergeguard.models import Symbol, SymbolType
        symbols = [
            Symbol(name="func_a", symbol_type=SymbolType.FUNCTION, file_path="f.py", start_line=10, end_line=20),
            Symbol(name="func_b", symbol_type=SymbolType.FUNCTION, file_path="f.py", start_line=25, end_line=35),
        ]
        affected = map_diff_to_symbols(symbols, [(15, 18)])
        assert len(affected) == 1
        assert affected[0].name == "func_a"
