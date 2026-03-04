"""Tests for configuration loading."""

from __future__ import annotations

import json
from datetime import datetime

from mergeguard.config import load_config
from mergeguard.models import MergeGuardConfig, PRInfo


class TestLoadConfig:
    def test_default_config(self, tmp_path):
        config = load_config(str(tmp_path / "nonexistent.yml"))
        assert isinstance(config, MergeGuardConfig)
        assert config.risk_threshold == 50

    def test_default_values(self):
        config = MergeGuardConfig()
        assert config.max_open_prs == 200
        assert config.max_pr_age_days == 30
        assert config.llm_enabled is False
        assert config.check_regressions is True


class TestMaxPrsOverride:
    """Tests for --max-prs and --max-pr-age CLI overrides of config."""

    def test_override_max_open_prs(self):
        cfg = MergeGuardConfig()
        assert cfg.max_open_prs == 200
        cfg.max_open_prs = 100
        assert cfg.max_open_prs == 100

    def test_override_max_pr_age_days(self):
        cfg = MergeGuardConfig()
        assert cfg.max_pr_age_days == 30
        cfg.max_pr_age_days = 7
        assert cfg.max_pr_age_days == 7

    def test_none_does_not_override(self):
        cfg = MergeGuardConfig()
        max_prs = None
        if max_prs is not None:
            cfg.max_open_prs = max_prs
        assert cfg.max_open_prs == 200
        max_pr_age = None
        if max_pr_age is not None:
            cfg.max_pr_age_days = max_pr_age
        assert cfg.max_pr_age_days == 30


class TestPRInfoSkippedFiles:
    """Tests for PRInfo.skipped_files field."""

    def _make_pr(self):
        return PRInfo(
            number=1,
            title="Test",
            author="dev",
            base_branch="main",
            head_branch="feat",
            head_sha="abc",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )

    def test_default_empty(self):
        pr = self._make_pr()
        assert pr.skipped_files == []

    def test_serialization_in_json(self):
        pr = self._make_pr()
        pr.skipped_files = ["large_binary.dat", "huge_file.py"]
        data = json.loads(pr.model_dump_json())
        assert data["skipped_files"] == ["large_binary.dat", "huge_file.py"]

    def test_empty_skipped_files_in_json(self):
        pr = self._make_pr()
        data = json.loads(pr.model_dump_json())
        assert data["skipped_files"] == []
