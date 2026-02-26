"""Tests for regression detection module."""
from __future__ import annotations
import pytest


class TestDetectRegressions:
    @pytest.mark.skip(reason="Requires SQLite fixture setup")
    def test_detect_removal_regression(self):
        pass

    @pytest.mark.skip(reason="Requires SQLite fixture setup")
    def test_detect_migration_regression(self):
        pass

    @pytest.mark.skip(reason="Requires SQLite fixture setup")
    def test_no_regressions(self):
        pass
