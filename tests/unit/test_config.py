"""Tests for configuration loading."""
from __future__ import annotations
import pytest
from mergeguard.config import load_config
from mergeguard.models import MergeGuardConfig


class TestLoadConfig:
    def test_default_config(self, tmp_path):
        config = load_config(str(tmp_path / "nonexistent.yml"))
        assert isinstance(config, MergeGuardConfig)
        assert config.risk_threshold == 50

    def test_default_values(self):
        config = MergeGuardConfig()
        assert config.max_open_prs == 30
        assert config.llm_enabled is False
        assert config.check_regressions is True
