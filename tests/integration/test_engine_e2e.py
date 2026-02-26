"""End-to-end integration tests for the MergeGuard engine."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from mergeguard.core.engine import MergeGuardEngine
from mergeguard.models import (
    ChangedFile,
    ConflictSeverity,
    FileChangeStatus,
    MergeGuardConfig,
    PRInfo,
)


def _make_pr(number, title="PR", author="dev", changed_files=None):
    pr = PRInfo(
        number=number,
        title=title,
        author=author,
        base_branch="main",
        head_branch=f"feature/{number}",
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 15),
        updated_at=datetime(2026, 1, 16),
    )
    if changed_files:
        pr.changed_files = changed_files
    return pr


PYTHON_SOURCE = """\
def process_data(items):
    result = []
    for item in items:
        result.append(item * 2)
    return result

def validate_input(data):
    if not data:
        raise ValueError("empty")
    return True
"""

PATCH_OVERLAPPING = "@@ -1,5 +1,6 @@\n def process_data(items):\n     result = []\n     for item in items:\n-        result.append(item * 2)\n+        result.append(item * 3)\n+        print(item)\n     return result\n"
PATCH_NON_OVERLAPPING = "@@ -7,4 +7,5 @@\n def validate_input(data):\n     if not data:\n         raise ValueError(\"empty\")\n+    print(\"validating\")\n     return True\n"


class TestEngineE2E:
    @patch("mergeguard.core.engine.GitHubClient")
    def test_full_analysis_pipeline(self, MockClientClass):
        """Test the complete analysis pipeline with mock data."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(1, "Add feature", "alice")
        other_pr = _make_pr(2, "Fix bug", "bob")

        target_files = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]
        other_files = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=3, deletions=1, patch=PATCH_OVERLAPPING,
            )
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 1 else other_files
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(1)

        assert report.pr.number == 1
        assert report.risk_score >= 0
        assert report.analysis_duration_ms > 0

    @patch("mergeguard.core.engine.GitHubClient")
    def test_analysis_with_no_conflicts(self, MockClientClass):
        """Two PRs that modify completely different files should have no conflicts."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(10, "Add auth")
        other_pr = _make_pr(11, "Add logging")

        target_files = [
            ChangedFile(
                path="src/auth.py", status=FileChangeStatus.MODIFIED,
                additions=10, deletions=0, patch=PATCH_OVERLAPPING,
            )
        ]
        other_files = [
            ChangedFile(
                path="src/logging.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=0, patch=PATCH_NON_OVERLAPPING,
            )
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 10 else other_files
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(10)

        assert len(report.conflicts) == 0
        assert 11 in report.no_conflict_prs

    @patch("mergeguard.core.engine.GitHubClient")
    def test_analysis_with_critical_conflict(self, MockClientClass):
        """Two PRs modifying the same function should produce a conflict."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(20, "Optimize process_data")
        other_pr = _make_pr(21, "Refactor process_data")

        shared_file = ChangedFile(
            path="src/app.py", status=FileChangeStatus.MODIFIED,
            additions=5, deletions=2, patch=PATCH_OVERLAPPING,
        )

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.return_value = [shared_file]
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(20)

        # Both PRs modify the same file with overlapping lines, so there should be conflicts
        assert len(report.conflicts) >= 1
        assert report.risk_score > 0
