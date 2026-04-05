"""Tests for GitLocalClient argument safety."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mergeguard.integrations.git_local import GitLocalClient


@pytest.fixture
def git_client(tmp_path):
    """Create a GitLocalClient with a fake .git directory."""
    (tmp_path / ".git").mkdir()
    return GitLocalClient(tmp_path)


class TestArgumentSafety:
    """Verify that user-controlled args cannot be interpreted as flags."""

    def test_get_diff_uses_double_dash(self, git_client):
        with patch.object(git_client, "_run", return_value="") as mock_run:
            git_client.get_diff("main", "HEAD")
            cmd = mock_run.call_args[0][0]
            assert "--" in cmd
            dash_idx = cmd.index("--")
            assert cmd[dash_idx + 1] == "main...HEAD"

    def test_get_file_content_uses_double_dash(self, git_client):
        with patch.object(git_client, "_run", return_value="content") as mock_run:
            git_client.get_file_content("src/main.py", "abc123")
            cmd = mock_run.call_args[0][0]
            assert "--" in cmd

    def test_get_changed_files_uses_double_dash(self, git_client):
        with patch.object(git_client, "_run", return_value="file.py\n") as mock_run:
            git_client.get_changed_files("main", "HEAD")
            cmd = mock_run.call_args[0][0]
            assert "--" in cmd

    def test_get_merge_base_uses_double_dash(self, git_client):
        with patch.object(git_client, "_run", return_value="abc123\n") as mock_run:
            git_client.get_merge_base("main", "feature")
            cmd = mock_run.call_args[0][0]
            assert "--" in cmd
