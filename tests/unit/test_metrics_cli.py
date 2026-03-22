"""Tests for the metrics CLI command."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mergeguard.cli import main
from mergeguard.models import DORAMetrics, DORAReport


@pytest.fixture
def runner():
    return CliRunner()


def _make_dora_report(repo: str = "owner/repo") -> DORAReport:
    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)
    return DORAReport(
        repo=repo,
        generated_at=now,
        windows=[
            DORAMetrics(
                window_days=7,
                period_start=datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC),
                period_end=now,
                merge_count=10,
                merges_per_day=1.43,
                total_prs_analyzed=15,
                prs_with_conflicts=3,
                conflict_rate=0.2,
                mean_resolution_time_hours=12.5,
                median_resolution_time_hours=8.0,
                p90_resolution_time_hours=24.0,
                mttrc_hours=12.5,
                unresolved_count=2,
            ),
            DORAMetrics(
                window_days=30,
                period_start=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
                period_end=now,
                merge_count=45,
                merges_per_day=1.5,
                total_prs_analyzed=60,
                prs_with_conflicts=12,
                conflict_rate=0.2,
                mean_resolution_time_hours=18.0,
                median_resolution_time_hours=10.0,
                p90_resolution_time_hours=48.0,
                mttrc_hours=18.0,
                unresolved_count=2,
            ),
        ],
    )


class TestMetricsCommand:
    @patch("mergeguard.cli._auto_detect_repo", return_value="owner/repo")
    @patch("mergeguard.core.metrics.compute_dora_metrics")
    @patch("mergeguard.config.load_config")
    def test_terminal_output(self, mock_config, mock_compute, mock_repo, runner):
        cfg = MagicMock()
        cfg.metrics.enabled = True
        cfg.metrics.time_windows = [7, 30]
        mock_config.return_value = cfg
        mock_compute.return_value = _make_dora_report()

        result = runner.invoke(main, ["metrics"])
        assert result.exit_code == 0
        assert "DORA Metrics" in result.output
        assert "Merge Count" in result.output
        assert "Conflict Rate" in result.output
        assert "MTTRC" in result.output

    @patch("mergeguard.cli._auto_detect_repo", return_value="owner/repo")
    @patch("mergeguard.core.metrics.compute_dora_metrics")
    @patch("mergeguard.config.load_config")
    def test_json_output(self, mock_config, mock_compute, mock_repo, runner):
        cfg = MagicMock()
        cfg.metrics.enabled = True
        cfg.metrics.time_windows = [7]
        mock_config.return_value = cfg
        mock_compute.return_value = _make_dora_report()

        result = runner.invoke(main, ["metrics", "--format", "json"])
        assert result.exit_code == 0
        assert '"repo": "owner/repo"' in result.output
        assert '"window_days": 7' in result.output

    @patch("mergeguard.cli._auto_detect_repo", return_value="owner/repo")
    @patch("mergeguard.core.metrics.compute_dora_metrics")
    @patch("mergeguard.config.load_config")
    def test_html_output(self, mock_config, mock_compute, mock_repo, runner):
        cfg = MagicMock()
        cfg.metrics.enabled = True
        cfg.metrics.time_windows = [7]
        mock_config.return_value = cfg
        mock_compute.return_value = _make_dora_report()

        result = runner.invoke(main, ["metrics", "--format", "html"])
        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.output
        assert "DORA Metrics" in result.output
        assert "Chart.js" in result.output or "chart.js" in result.output

    @patch("mergeguard.cli._auto_detect_repo", return_value="owner/repo")
    @patch("mergeguard.core.metrics.compute_dora_metrics")
    @patch("mergeguard.config.load_config")
    def test_custom_windows(self, mock_config, mock_compute, mock_repo, runner):
        cfg = MagicMock()
        cfg.metrics.enabled = True
        cfg.metrics.time_windows = [7, 30, 90]
        mock_config.return_value = cfg
        mock_compute.return_value = _make_dora_report()

        result = runner.invoke(main, ["metrics", "-w", "14", "-w", "60"])
        assert result.exit_code == 0
        mock_compute.assert_called_once_with("owner/repo", [14, 60])

    @patch("mergeguard.cli._auto_detect_repo", return_value="owner/repo")
    @patch("mergeguard.config.load_config")
    def test_disabled_metrics_shows_warning(self, mock_config, mock_repo, runner):
        cfg = MagicMock()
        cfg.metrics.enabled = False
        mock_config.return_value = cfg

        result = runner.invoke(main, ["metrics"])
        assert result.exit_code == 0
        assert "not enabled" in result.output
