"""Tests for similarity analysis module."""
from __future__ import annotations
import pytest
from mergeguard.analysis.similarity import jaccard_similarity, symbol_name_similarity, detect_potential_duplications
from mergeguard.models import Symbol, SymbolType


class TestJaccardSimilarity:
    def test_identical_sets(self):
        assert jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self):
        assert jaccard_similarity({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        result = jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        assert 0.0 < result < 1.0

    def test_empty_sets(self):
        assert jaccard_similarity(set(), set()) == 0.0
