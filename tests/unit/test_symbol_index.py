"""Tests for symbol_index module."""

from __future__ import annotations

from mergeguard.analysis.symbol_index import SymbolIndex
from mergeguard.models import SymbolType


SAMPLE_PYTHON = """\
def greet(name):
    return f"Hello, {name}"

def farewell(name):
    return f"Goodbye, {name}"

class UserService:
    def get_user(self, user_id):
        pass

    def delete_user(self, user_id):
        pass
"""


class TestSymbolIndex:
    def test_get_symbols_returns_results(self):
        index = SymbolIndex()
        symbols = index.get_symbols("service.py", SAMPLE_PYTHON, ref="main")
        names = {s.name for s in symbols}
        assert "greet" in names
        assert "farewell" in names

    def test_cache_hit(self):
        index = SymbolIndex()
        first = index.get_symbols("service.py", SAMPLE_PYTHON, ref="abc123")
        second = index.get_symbols("service.py", SAMPLE_PYTHON, ref="abc123")
        # Same object returned from cache
        assert first is second

    def test_cache_miss_different_ref(self):
        index = SymbolIndex()
        first = index.get_symbols("service.py", SAMPLE_PYTHON, ref="abc")
        second = index.get_symbols("service.py", SAMPLE_PYTHON, ref="def")
        # Different refs produce separate cache entries
        assert first is not second

    def test_find_symbol(self):
        index = SymbolIndex()
        index.get_symbols("service.py", SAMPLE_PYTHON, ref="main")
        sym = index.find_symbol("service.py", "greet", ref="main")
        assert sym is not None
        assert sym.name == "greet"
        assert sym.symbol_type == SymbolType.FUNCTION

    def test_find_symbol_not_found(self):
        index = SymbolIndex()
        index.get_symbols("service.py", SAMPLE_PYTHON, ref="main")
        sym = index.find_symbol("service.py", "nonexistent", ref="main")
        assert sym is None

    def test_clear_cache(self):
        index = SymbolIndex()
        index.get_symbols("service.py", SAMPLE_PYTHON, ref="main")
        index.clear()
        # After clearing, find_symbol returns None (no cached data)
        assert index.find_symbol("service.py", "greet", ref="main") is None

    def test_clear_file(self):
        index = SymbolIndex()
        index.get_symbols("a.py", SAMPLE_PYTHON, ref="main")
        index.get_symbols("b.py", SAMPLE_PYTHON, ref="main")
        index.clear_file("a.py", ref="main")
        # a.py cleared, b.py still cached
        assert index.find_symbol("a.py", "greet", ref="main") is None
        assert index.find_symbol("b.py", "greet", ref="main") is not None
