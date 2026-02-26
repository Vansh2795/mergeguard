"""CLI smoke tests."""
from __future__ import annotations

from click.testing import CliRunner

from mergeguard.cli import main


class TestCLI:
    def test_analyze_command_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "Analyze a PR" in result.output

    def test_map_command_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["map", "--help"])
        assert result.exit_code == 0
        assert "collision map" in result.output.lower() or "open PRs" in result.output

    def test_dashboard_command_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["dashboard", "--help"])
        assert result.exit_code == 0
        assert "risk scores" in result.output.lower() or "open PRs" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
