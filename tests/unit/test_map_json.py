"""Tests for the map command's JSON output."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mergeguard.cli import main
from mergeguard.models import ChangedFile, FileChangeStatus, PRInfo


def _make_pr(number: int, title: str, files: list[str]) -> PRInfo:
    return PRInfo(
        number=number,
        title=title,
        author="dev",
        base_branch="main",
        head_branch=f"feature/{number}",
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
        changed_files=[ChangedFile(path=f, status=FileChangeStatus.MODIFIED) for f in files],
    )


def _create_mock_client(prs: list[PRInfo]) -> MagicMock:
    client = MagicMock()
    client.get_open_prs.return_value = prs
    client.get_pr_files.side_effect = lambda n: next(p.changed_files for p in prs if p.number == n)
    return client


def _invoke_map(prs: list[PRInfo], extra_args: list[str] | None = None) -> str:
    """Invoke the map command with a mocked SCM client and return stdout."""
    client = _create_mock_client(prs)
    args = ["map", "--repo", "owner/repo", "--token", "fake", *(extra_args or [])]
    runner = CliRunner()
    with patch("mergeguard.cli._create_client", return_value=client):
        result = runner.invoke(
            main,
            args,
            catch_exceptions=False,
            obj={"platform": "github", "gitlab_url": "https://gitlab.com"},
        )
    assert result.exit_code == 0, result.output
    return result.output


class TestMapJsonOutput:
    def test_json_structure(self):
        prs = [_make_pr(1, "PR one", ["a.py"]), _make_pr(2, "PR two", ["b.py"])]
        data = json.loads(_invoke_map(prs, ["--format", "json"]))
        assert "repo" in data
        assert "prs" in data
        assert "overlaps" in data

    def test_no_overlaps(self):
        prs = [_make_pr(1, "PR one", ["a.py"]), _make_pr(2, "PR two", ["b.py"])]
        data = json.loads(_invoke_map(prs, ["--format", "json"]))
        assert data["overlaps"] == []

    def test_with_overlaps(self):
        prs = [
            _make_pr(1, "PR one", ["shared.py", "a.py"]),
            _make_pr(2, "PR two", ["shared.py", "b.py"]),
        ]
        data = json.loads(_invoke_map(prs, ["--format", "json"]))
        assert len(data["overlaps"]) == 1
        overlap = data["overlaps"][0]
        assert overlap["pr_a"] == 1
        assert overlap["pr_b"] == 2
        assert "shared.py" in overlap["shared_files"]

    def test_deduplication(self):
        """Each pair should appear exactly once, not once per direction."""
        prs = [
            _make_pr(1, "PR one", ["shared.py"]),
            _make_pr(2, "PR two", ["shared.py"]),
        ]
        data = json.loads(_invoke_map(prs, ["--format", "json"]))
        assert len(data["overlaps"]) == 1

    def test_pr_list(self):
        prs = [_make_pr(1, "PR one", ["a.py"]), _make_pr(2, "PR two", ["b.py"])]
        data = json.loads(_invoke_map(prs, ["--format", "json"]))
        assert len(data["prs"]) == 2
        assert data["prs"][0]["number"] == 1
        assert data["prs"][1]["number"] == 2

    def test_repo_in_output(self):
        prs = [_make_pr(1, "PR one", ["a.py"])]
        data = json.loads(_invoke_map(prs, ["--format", "json"]))
        assert data["repo"] == "owner/repo"

    def test_multiple_shared_files(self):
        prs = [
            _make_pr(1, "PR one", ["x.py", "y.py", "z.py"]),
            _make_pr(2, "PR two", ["x.py", "y.py"]),
        ]
        data = json.loads(_invoke_map(prs, ["--format", "json"]))
        assert len(data["overlaps"]) == 1
        assert sorted(data["overlaps"][0]["shared_files"]) == ["x.py", "y.py"]

    def test_terminal_format_default(self):
        """Default format should not produce JSON."""
        prs = [_make_pr(1, "PR one", ["a.py"])]
        output = _invoke_map(prs)
        with pytest.raises(json.JSONDecodeError):
            json.loads(output)
