"""Integration test: full GitLab MR analysis flow with mocked API."""

from __future__ import annotations

import httpx
import respx

from mergeguard.integrations.gitlab_client import GitLabClient
from mergeguard.models import FileChangeStatus

_BASE = "https://gitlab.com/api/v4/projects/myorg%2Fbackend"

_MR_LIST = [
    {
        "iid": 1,
        "title": "Add authentication",
        "author": {"username": "alice"},
        "source_branch": "feature/auth",
        "target_branch": "main",
        "sha": "aaa111",
        "source_project_id": 10,
        "target_project_id": 10,
        "created_at": "2026-01-15T10:00:00Z",
        "updated_at": "2026-01-16T14:30:00Z",
        "labels": ["feature"],
        "description": "JWT auth",
    },
    {
        "iid": 2,
        "title": "Refactor user model",
        "author": {"username": "bob"},
        "source_branch": "refactor/user",
        "target_branch": "main",
        "sha": "bbb222",
        "source_project_id": 10,
        "target_project_id": 10,
        "created_at": "2026-01-14T09:00:00Z",
        "updated_at": "2026-01-16T11:00:00Z",
        "labels": ["refactor"],
        "description": "Clean up user model",
    },
]

_MR1_DIFFS = [
    {
        "old_path": "src/auth.py",
        "new_path": "src/auth.py",
        "diff": (
            "@@ -1,3 +1,10 @@\n import os\n+import jwt\n+\n"
            "+def authenticate(token):\n+    return jwt.decode(token)\n"
        ),
        "new_file": False,
        "renamed_file": False,
        "deleted_file": False,
    },
]

_MR2_DIFFS = [
    {
        "old_path": "src/user.py",
        "new_path": "src/user.py",
        "diff": (
            "@@ -5,8 +5,12 @@\n class User:\n-    name: str\n+    username: str\n+    email: str\n"
        ),
        "new_file": False,
        "renamed_file": False,
        "deleted_file": False,
    },
]


class TestFullMRAnalysisFlow:
    @respx.mock
    def test_complete_flow(self):
        """Simulate a full GitLab MR analysis: list MRs, fetch diffs, get file content."""
        client = GitLabClient("fake-token", "myorg/backend")

        # Mock MR list
        respx.get(f"{_BASE}/merge_requests").mock(return_value=httpx.Response(200, json=_MR_LIST))

        # Mock MR details
        respx.get(f"{_BASE}/merge_requests/1").mock(
            return_value=httpx.Response(200, json=_MR_LIST[0])
        )
        respx.get(f"{_BASE}/merge_requests/2").mock(
            return_value=httpx.Response(200, json=_MR_LIST[1])
        )

        # Mock diffs
        respx.get(f"{_BASE}/merge_requests/1/diffs").mock(
            return_value=httpx.Response(200, json=_MR1_DIFFS)
        )
        respx.get(f"{_BASE}/merge_requests/2/diffs").mock(
            return_value=httpx.Response(200, json=_MR2_DIFFS)
        )

        # Mock file content
        respx.get(f"{_BASE}/repository/files/src%2Fauth.py/raw").mock(
            return_value=httpx.Response(200, text="import os\n\ndef old_auth(): pass\n")
        )
        respx.get(f"{_BASE}/repository/files/src%2Fuser.py/raw").mock(
            return_value=httpx.Response(200, text="class User:\n    name: str\n")
        )

        # Step 1: List open MRs
        open_prs = client.get_open_prs(max_count=10)
        assert len(open_prs) == 2
        assert open_prs[0].number == 1
        assert open_prs[0].title == "Add authentication"
        assert open_prs[1].number == 2

        # Step 2: Fetch target MR detail
        target = client.get_pr(1)
        assert target.number == 1
        assert target.head_sha == "aaa111"

        # Step 3: Get files for both MRs
        files1 = client.get_pr_files(1)
        assert len(files1) == 1
        assert files1[0].path == "src/auth.py"
        assert files1[0].status == FileChangeStatus.MODIFIED
        assert files1[0].patch is not None

        files2 = client.get_pr_files(2)
        assert len(files2) == 1
        assert files2[0].path == "src/user.py"

        # Step 4: Get unified diff
        diff1 = client.get_pr_diff(1)
        assert "diff --git" in diff1
        assert "+import jwt" in diff1

        # Step 5: Get file content at base branch
        content = client.get_file_content("src/auth.py", "main")
        assert "import os" in content
        assert "old_auth" in content

        # Step 6: File content for non-existent file
        respx.get(f"{_BASE}/repository/files/nonexistent.py/raw").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        assert client.get_file_content("nonexistent.py", "main") is None
