"""Unit tests for GitLab client using respx to mock httpx."""
from __future__ import annotations

import httpx
import pytest
import respx
from datetime import datetime, timezone

from mergeguard.integrations.gitlab_client import GitLabClient
from mergeguard.models import FileChangeStatus


_BASE = "https://gitlab.com/api/v4/projects/mygroup%2Fmyproject"

_SAMPLE_MR = {
    "iid": 10,
    "title": "Add feature X",
    "author": {"username": "alice"},
    "source_branch": "feature/x",
    "target_branch": "main",
    "sha": "abc123",
    "source_project_id": 1,
    "target_project_id": 1,
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-01-16T14:30:00Z",
    "labels": ["enhancement"],
    "description": "Adds feature X",
}

_SAMPLE_MR_FORK = {
    **_SAMPLE_MR,
    "iid": 11,
    "source_project_id": 2,
    "target_project_id": 1,
}

_SAMPLE_DIFF = {
    "old_path": "src/app.py",
    "new_path": "src/app.py",
    "diff": "@@ -1,5 +1,6 @@\n import os\n+import sys\n \n def main():\n     pass\n",
    "new_file": False,
    "renamed_file": False,
    "deleted_file": False,
}

_SAMPLE_DIFF_ADDED = {
    "old_path": "src/new.py",
    "new_path": "src/new.py",
    "diff": "@@ -0,0 +1,3 @@\n+def hello():\n+    return 'world'\n",
    "new_file": True,
    "renamed_file": False,
    "deleted_file": False,
}


@pytest.fixture
def client():
    return GitLabClient("fake-token", "mygroup/myproject")


class TestGetOpenPRs:
    @respx.mock
    def test_basic(self, client):
        respx.get(f"{_BASE}/merge_requests").mock(
            return_value=httpx.Response(200, json=[_SAMPLE_MR])
        )
        prs = client.get_open_prs(max_count=10)
        assert len(prs) == 1
        assert prs[0].number == 10
        assert prs[0].title == "Add feature X"
        assert prs[0].author == "alice"
        assert prs[0].head_branch == "feature/x"
        assert prs[0].base_branch == "main"
        assert prs[0].labels == ["enhancement"]

    @respx.mock
    def test_max_count_respected(self, client):
        mrs = [{**_SAMPLE_MR, "iid": i} for i in range(5)]
        respx.get(f"{_BASE}/merge_requests").mock(
            return_value=httpx.Response(200, json=mrs)
        )
        prs = client.get_open_prs(max_count=3)
        assert len(prs) == 3

    @respx.mock
    def test_pagination(self, client):
        page1 = [{**_SAMPLE_MR, "iid": 1}]
        page2 = [{**_SAMPLE_MR, "iid": 2}]
        respx.get(f"{_BASE}/merge_requests").mock(
            side_effect=[
                httpx.Response(200, json=page1, headers={"x-next-page": "2"}),
                httpx.Response(200, json=page2, headers={}),
            ]
        )
        prs = client.get_open_prs(max_count=10)
        assert len(prs) == 2
        assert prs[0].number == 1
        assert prs[1].number == 2


class TestGetPR:
    @respx.mock
    def test_single_mr(self, client):
        respx.get(f"{_BASE}/merge_requests/10").mock(
            return_value=httpx.Response(200, json=_SAMPLE_MR)
        )
        pr = client.get_pr(10)
        assert pr.number == 10
        assert pr.head_sha == "abc123"
        assert pr.is_fork is False


class TestGetPRFiles:
    @respx.mock
    def test_files_mapping(self, client):
        respx.get(f"{_BASE}/merge_requests/10/diffs").mock(
            return_value=httpx.Response(200, json=[_SAMPLE_DIFF, _SAMPLE_DIFF_ADDED])
        )
        files = client.get_pr_files(10)
        assert len(files) == 2
        assert files[0].path == "src/app.py"
        assert files[0].status == FileChangeStatus.MODIFIED
        assert files[0].additions == 1
        assert files[0].deletions == 0
        assert files[1].path == "src/new.py"
        assert files[1].status == FileChangeStatus.ADDED


class TestGetPRDiff:
    @respx.mock
    def test_reassembled_diff(self, client):
        respx.get(f"{_BASE}/merge_requests/10/diffs").mock(
            return_value=httpx.Response(200, json=[_SAMPLE_DIFF])
        )
        diff = client.get_pr_diff(10)
        assert "diff --git a/src/app.py b/src/app.py" in diff
        assert "--- a/src/app.py" in diff
        assert "+++ b/src/app.py" in diff
        assert "+import sys" in diff


class TestGetFileContent:
    @respx.mock
    def test_raw_content(self, client):
        encoded = "src%2Fapp.py"
        respx.get(f"{_BASE}/repository/files/{encoded}/raw").mock(
            return_value=httpx.Response(200, text="import os\n\ndef main(): pass\n")
        )
        content = client.get_file_content("src/app.py", "main")
        assert "import os" in content

    @respx.mock
    def test_404_returns_none(self, client):
        encoded = "nonexistent.py"
        respx.get(f"{_BASE}/repository/files/{encoded}/raw").mock(
            return_value=httpx.Response(404, json={"message": "404 File Not Found"})
        )
        result = client.get_file_content("nonexistent.py", "main")
        assert result is None


class TestPostComment:
    @respx.mock
    def test_new_comment(self, client):
        notes_url = f"{_BASE}/merge_requests/10/notes"
        respx.get(notes_url).mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.post(notes_url).mock(
            return_value=httpx.Response(201, json={"id": 1})
        )
        client.post_pr_comment(10, "Test report")

    @respx.mock
    def test_update_existing_comment(self, client):
        notes_url = f"{_BASE}/merge_requests/10/notes"
        existing_note = {
            "id": 99,
            "body": "<!-- mergeguard-report -->\nOld report",
        }
        respx.get(notes_url).mock(
            return_value=httpx.Response(200, json=[existing_note])
        )
        respx.put(f"{notes_url}/99").mock(
            return_value=httpx.Response(200, json={"id": 99})
        )
        client.post_pr_comment(10, "Updated report")


class TestForkDetection:
    @respx.mock
    def test_fork_detected(self, client):
        respx.get(f"{_BASE}/merge_requests/11").mock(
            return_value=httpx.Response(200, json=_SAMPLE_MR_FORK)
        )
        pr = client.get_pr(11)
        assert pr.is_fork is True

    @respx.mock
    def test_non_fork(self, client):
        respx.get(f"{_BASE}/merge_requests/10").mock(
            return_value=httpx.Response(200, json=_SAMPLE_MR)
        )
        pr = client.get_pr(10)
        assert pr.is_fork is False
