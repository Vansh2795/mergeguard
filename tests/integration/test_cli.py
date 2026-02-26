"""CLI smoke tests."""
from __future__ import annotations
import pytest
from click.testing import CliRunner


class TestCLI:
    @pytest.mark.skip(reason="Requires GitHub API mocking setup")
    def test_analyze_command_help(self):
        from mergeguard.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "Analyze a PR" in result.output

    @pytest.mark.skip(reason="Requires GitHub API mocking setup")
    def test_map_command_help(self):
        from mergeguard.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["map", "--help"])
        assert result.exit_code == 0

    @pytest.mark.skip(reason="Requires GitHub API mocking setup")
    def test_dashboard_command_help(self):
        from mergeguard.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["dashboard", "--help"])
        assert result.exit_code == 0

    @pytest.mark.skip(reason="Requires GitHub API mocking setup")
    def test_version(self):
        from mergeguard.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
