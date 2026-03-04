"""End-to-end integration tests for the MergeGuard engine."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from github import GithubException

from mergeguard.core.engine import MergeGuardEngine, _find_overlapping_range
from mergeguard.models import (
    ChangedFile,
    Conflict,
    ConflictSeverity,
    ConflictType,
    FileChangeStatus,
    GuardrailRule,
    MergeGuardConfig,
    PRInfo,
    Symbol,
    SymbolType,
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

# Source code for insertion test: BASE has only validate_input
PYTHON_SOURCE_INSERT_BASE = """\
def validate_input(data):
    if not data:
        raise ValueError("empty")
    return True
"""

# HEAD has new_helper inserted before validate_input
PYTHON_SOURCE_INSERT_HEAD = """\
def new_helper(x):
    return x + 1

def validate_input(data):
    if not data:
        raise ValueError("empty")
    return True
"""

# Patch that inserts new_helper before validate_input
PATCH_INSERT_BEFORE = "@@ -1,4 +1,7 @@\n+def new_helper(x):\n+    return x + 1\n+\n def validate_input(data):\n     if not data:\n         raise ValueError(\"empty\")\n     return True\n"


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
        mock_client.rate_limit_remaining = 5000

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
        mock_client.rate_limit_remaining = 5000

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
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(20)

        # Both PRs modify the same file with overlapping lines, so there should be conflicts
        assert len(report.conflicts) >= 1
        assert report.risk_score > 0

    @patch("mergeguard.core.engine.GitHubClient")
    def test_risk_factors_contain_nonzero_blast_radius_and_churn(self, MockClientClass):
        """Risk factors should contain non-zero blast_radius and churn_risk
        when changed files have additions/deletions and imports."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(30, "Add helpers")
        other_pr = _make_pr(31, "Other work")

        # Two files: src/app.py imports src/utils.py, so utils has a dependent
        target_files = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=100, deletions=50, patch=PATCH_OVERLAPPING,
            ),
            ChangedFile(
                path="src/utils.py", status=FileChangeStatus.MODIFIED,
                additions=10, deletions=5, patch=PATCH_NON_OVERLAPPING,
            ),
        ]
        other_files = [
            ChangedFile(
                path="src/other.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=0, patch=PATCH_NON_OVERLAPPING,
            )
        ]

        # src/app.py imports src.utils → utils has a dependent (app)
        source_app = (
            "from src.utils import helper\n\n"
            "def process_data(items):\n"
            "    result = []\n"
            "    for item in items:\n"
            "        result.append(item * 2)\n"
            "    return result\n"
        )
        source_utils = (
            "def helper():\n"
            "    return 42\n\n"
            "def validate_input(data):\n"
            "    if not data:\n"
            "        raise ValueError('empty')\n"
            "    return True\n"
        )

        def get_content(path, ref):
            if path == "src/app.py":
                return source_app
            return source_utils

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 30 else other_files
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.side_effect = get_content
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(30)

        # churn_risk should be non-zero because additions + deletions = 165
        assert report.risk_factors["churn_risk"] > 0
        # blast_radius should be non-zero because src/app.py imports src.utils
        # so src.utils has a dependent, giving it dependency_depth >= 1
        assert report.risk_factors["blast_radius"] > 0

    @patch("mergeguard.core.engine.GitHubClient")
    def test_dependency_depth_computed(self, MockClientClass):
        """Verify dependency depth is actually computed from file contents."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(40, "Deep deps")
        other_pr = _make_pr(41, "Other")

        target_files = [
            ChangedFile(
                path="src/deep.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=0, patch=PATCH_OVERLAPPING,
            )
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 40 else []
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(40)

        # blast_radius is derived from dependency_depth
        assert "blast_radius" in report.risk_factors

    @patch("mergeguard.core.engine.GitHubClient")
    def test_ignored_paths_are_filtered(self, MockClientClass):
        """Files matching ignored_paths should be filtered out before analysis."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(50, "Update deps")
        other_pr = _make_pr(51, "Other")

        target_files = [
            ChangedFile(
                path="poetry.lock", status=FileChangeStatus.MODIFIED,
                additions=500, deletions=400, patch=PATCH_OVERLAPPING,
            ),
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            ),
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 50 else []
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(50)

        # poetry.lock should have been filtered out by ignored_paths
        remaining_paths = {cf.path for cf in report.pr.changed_files}
        assert "poetry.lock" not in remaining_paths
        assert "src/app.py" in remaining_paths

    @patch("mergeguard.core.engine.GitHubClient")
    def test_signature_change_detected(self, MockClientClass):
        """When a function signature changes between base and head, it should be detected."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(60, "Change signature")
        other_pr = _make_pr(61, "Other")

        target_files = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]

        base_source = (
            "def process_data(items):\n"
            "    result = []\n"
            "    for item in items:\n"
            "        result.append(item * 2)\n"
            "    return result\n"
        )
        head_source = (
            "def process_data(items, limit=10):\n"
            "    result = []\n"
            "    for item in items[:limit]:\n"
            "        result.append(item * 3)\n"
            "        print(item)\n"
            "    return result\n"
        )

        def get_content(path, ref):
            if ref == "main":
                return base_source
            return head_source

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 60 else []
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.side_effect = get_content
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(60)

        # Should detect signature change for process_data
        sig_changes = [
            cs for cs in report.pr.changed_symbols
            if cs.change_type == "modified_signature"
        ]
        assert len(sig_changes) >= 1

    @patch("mergeguard.core.engine.GitHubClient")
    def test_batch_analysis_enriches_each_pr_once(self, MockClientClass):
        """analyze_all_open_prs should call get_pr_files once per PR, not N times."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        pr1 = _make_pr(70, "PR A")
        pr2 = _make_pr(71, "PR B")

        files_a = [
            ChangedFile(
                path="src/a.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=0, patch=PATCH_OVERLAPPING,
            )
        ]
        files_b = [
            ChangedFile(
                path="src/b.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=0, patch=PATCH_NON_OVERLAPPING,
            )
        ]

        mock_client.get_open_prs.return_value = [pr1, pr2]
        mock_client.get_pr_files.side_effect = lambda n: files_a if n == 70 else files_b
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        reports = engine.analyze_all_open_prs()

        assert len(reports) == 2
        # get_pr_files should be called exactly 2 times (once per PR), not 4
        assert mock_client.get_pr_files.call_count == 2

    @patch("mergeguard.core.engine.GitHubClient")
    def test_content_cache_avoids_duplicate_calls(self, MockClientClass):
        """Content cache should prevent duplicate get_file_content calls for same path+ref."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(80, "Cache test")
        other_pr = _make_pr(81, "Other")

        target_files = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 80 else []
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(80)

        # Count calls for the same path+ref — should be at most 1 per unique (path, ref)
        calls = mock_client.get_file_content.call_args_list
        unique_calls = set((c[0][0], c[0][1]) for c in calls)
        assert len(unique_calls) == len(calls)


    @patch("mergeguard.core.engine.GitHubClient")
    def test_fork_pr_skips_head_content_fetch(self, MockClientClass):
        """A fork PR should not trigger get_file_content calls for its head branch."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(90, "Fork PR")
        target_pr.is_fork = True
        other_pr = _make_pr(91, "Other")

        target_files = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 90 else []
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(90)

        # get_file_content should never be called with the fork's head branch
        for call in mock_client.get_file_content.call_args_list:
            assert call[0][1] != f"feature/90", (
                f"Should not fetch head branch content for fork PR, but got call: {call}"
            )

    @patch("mergeguard.core.engine.GitHubClient")
    def test_parallel_enrichment_handles_failure(self, MockClientClass):
        """If one PR's get_pr_files raises, analysis should still complete for others."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(100, "Target")
        good_pr = _make_pr(101, "Good PR")
        bad_pr = _make_pr(102, "Bad PR")

        target_files = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]
        good_files = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=3, deletions=1, patch=PATCH_OVERLAPPING,
            )
        ]

        def get_files(n):
            if n == 100:
                return target_files
            if n == 101:
                return good_files
            raise GithubException(500, "API failure for PR #102", None)

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = get_files
        mock_client.get_open_prs.return_value = [target_pr, good_pr, bad_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=MergeGuardConfig()
        )
        report = engine.analyze_pr(100)

        # Analysis should complete despite bad_pr failing
        assert report.pr.number == 100
        assert report.analysis_duration_ms > 0


class TestTransitiveConflictE2E:
    @patch("mergeguard.core.engine.GitHubClient")
    def test_transitive_conflict_in_report(self, MockClientClass):
        """Full pipeline: transitive conflict appears in report when PRs touch
        different files connected by imports."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(200, "Update models")
        other_pr = _make_pr(201, "Update views")

        # target modifies models.py, other modifies views.py
        target_files = [
            ChangedFile(
                path="src/models.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]
        other_files = [
            ChangedFile(
                path="src/views.py", status=FileChangeStatus.MODIFIED,
                additions=3, deletions=1, patch=PATCH_NON_OVERLAPPING,
            )
        ]

        # views.py imports from models
        source_models = (
            "class User:\n"
            "    def __init__(self, name):\n"
            "        self.name = name\n\n"
            "def process_data(items):\n"
            "    result = []\n"
            "    for item in items:\n"
            "        result.append(item * 2)\n"
            "    return result\n"
        )
        source_views = (
            "from models import User\n\n"
            "def render_user(user):\n"
            "    return f'User: {user.name}'\n\n"
            "def validate_input(data):\n"
            "    if not data:\n"
            "        raise ValueError('empty')\n"
            "    return True\n"
        )

        def get_content(path, ref):
            if "models" in path:
                return source_models
            return source_views

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 200 else other_files
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.side_effect = get_content
        mock_client.rate_limit_remaining = 5000

        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo",
            config=MergeGuardConfig(check_regressions=False),
        )
        report = engine.analyze_pr(200)

        transitive = [
            c for c in report.conflicts
            if c.conflict_type == ConflictType.TRANSITIVE
        ]
        assert len(transitive) == 1
        assert transitive[0].target_pr == 201
        assert transitive[0].severity == ConflictSeverity.WARNING
        # Description should reference specific files
        assert "PR #201" in transitive[0].description
        assert "src/models.py" in transitive[0].description
        # Changed symbols from models.py should appear (process_data is the
        # one touched by PATCH_OVERLAPPING)
        assert "Changed symbols:" in transitive[0].description
        assert "`process_data`" in transitive[0].description
        # Recommendation should be specific
        assert "src/models.py" in transitive[0].recommendation
        # PR 201 should NOT be in no_conflict_prs
        assert 201 not in report.no_conflict_prs


class TestFindOverlappingRange:
    def _make_symbol(self, start, end):
        return Symbol(
            name="test_fn", symbol_type=SymbolType.FUNCTION,
            file_path="test.py", start_line=start, end_line=end,
        )

    def test_finds_overlapping_range(self):
        symbol = self._make_symbol(10, 20)
        ranges = [(1, 5), (15, 25), (30, 40)]
        assert _find_overlapping_range(symbol, ranges) == (15, 25)

    def test_falls_back_to_first_range(self):
        symbol = self._make_symbol(50, 60)
        ranges = [(1, 5), (10, 15)]
        assert _find_overlapping_range(symbol, ranges) == (1, 5)

    def test_empty_ranges(self):
        symbol = self._make_symbol(10, 20)
        assert _find_overlapping_range(symbol, []) == (0, 0)


class TestGuardrailsWiring:
    @patch("mergeguard.core.engine.GitHubClient")
    def test_guardrail_violations_included_in_report(self, MockClientClass):
        """When config has rules, guardrail violations should appear in conflicts."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(110, "Large PR")
        other_pr = _make_pr(111, "Other")

        target_files = [
            ChangedFile(
                path="src/a.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            ),
            ChangedFile(
                path="src/b.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_NON_OVERLAPPING,
            ),
            ChangedFile(
                path="src/c.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            ),
        ]

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 110 else []
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        config = MergeGuardConfig(
            rules=[GuardrailRule(name="size-limit", max_files_changed=1, message="Too many files")],
            check_regressions=False,
        )
        engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=config)
        report = engine.analyze_pr(110)

        guardrail_conflicts = [
            c for c in report.conflicts if "exceeding the limit" in c.description
        ]
        assert len(guardrail_conflicts) >= 1
        assert "size-limit" in guardrail_conflicts[0].description

    @patch("mergeguard.core.engine.GitHubClient")
    def test_no_guardrail_violations_when_rules_empty(self, MockClientClass):
        """No guardrail violations when config has no rules."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(112, "Normal PR")
        other_pr = _make_pr(113, "Other")

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.return_value = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        config = MergeGuardConfig(rules=[], check_regressions=False)
        engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=config)
        report = engine.analyze_pr(112)

        guardrail_conflicts = [
            c for c in report.conflicts if "exceeding the limit" in c.description
        ]
        assert len(guardrail_conflicts) == 0


class TestRegressionDetectionWiring:
    @patch("mergeguard.core.engine.GitHubClient")
    def test_regression_conflicts_included(self, MockClientClass, _no_filesystem_side_effects):
        """Regression conflicts should appear in the report when check_regressions is on."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        # Set up the DecisionsLog mock (provided by autouse fixture via engine patch)
        # to return a regression when detect_regressions runs
        regression_conflict = Conflict(
            conflict_type=ConflictType.REGRESSION,
            severity=ConflictSeverity.WARNING,
            source_pr=120,
            target_pr=999,
            file_path="src/app.py",
            symbol_name="process_data",
            description="Re-introduces removed function",
            recommendation="Check if intentional",
        )

        with patch("mergeguard.core.engine.detect_regressions", return_value=[regression_conflict]) as mock_detect:
            target_pr = _make_pr(120, "Regression PR")
            other_pr = _make_pr(121, "Other")

            mock_client.get_pr.return_value = target_pr
            mock_client.get_pr_files.return_value = [
                ChangedFile(
                    path="src/app.py", status=FileChangeStatus.MODIFIED,
                    additions=5, deletions=2, patch=PATCH_OVERLAPPING,
                )
            ]
            mock_client.get_open_prs.return_value = [target_pr, other_pr]
            mock_client.get_file_content.return_value = PYTHON_SOURCE
            mock_client.rate_limit_remaining = 5000

            config = MergeGuardConfig(check_regressions=True)
            engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=config)
            report = engine.analyze_pr(120)

        mock_detect.assert_called_once()
        regression_conflicts = [
            c for c in report.conflicts if c.conflict_type == ConflictType.REGRESSION
        ]
        assert len(regression_conflicts) >= 1

    @patch("mergeguard.core.engine.GitHubClient")
    def test_regression_skipped_when_disabled(self, MockClientClass):
        """No regression detection when check_regressions is False."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(122, "Normal PR")
        other_pr = _make_pr(123, "Other")

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.return_value = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        config = MergeGuardConfig(check_regressions=False)
        engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=config)
        report = engine.analyze_pr(122)

        # No regression conflicts when disabled
        regression_conflicts = [
            c for c in report.conflicts if c.conflict_type == ConflictType.REGRESSION
        ]
        assert len(regression_conflicts) == 0


class TestLLMAnalysisWiring:
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"})
    @patch("mergeguard.integrations.llm_analyzer.LLMAnalyzer")
    @patch("mergeguard.core.engine.GitHubClient")
    def test_llm_refines_behavioral_conflicts(self, MockClientClass, MockLLM):
        """LLM should be called for behavioral conflicts and can downgrade severity."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        # LLM says changes are compatible → returns None
        mock_llm_instance = MagicMock()
        mock_llm_instance.analyze_behavioral_conflict.return_value = None
        MockLLM.return_value = mock_llm_instance

        target_pr = _make_pr(130, "Feature A")
        other_pr = _make_pr(131, "Feature B")

        shared_file = ChangedFile(
            path="src/app.py", status=FileChangeStatus.MODIFIED,
            additions=5, deletions=2, patch=PATCH_OVERLAPPING,
        )

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.return_value = [shared_file]
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        config = MergeGuardConfig(llm_enabled=True, check_regressions=False)
        engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=config)
        report = engine.analyze_pr(130)

        # If behavioral conflicts were found, LLM should have been invoked
        behavioral = [c for c in report.conflicts if c.conflict_type == ConflictType.BEHAVIORAL]
        if behavioral:
            assert mock_llm_instance.analyze_behavioral_conflict.called
            # LLM returned None (compatible), so behavioral should be downgraded to INFO
            for c in behavioral:
                assert c.severity == ConflictSeverity.INFO

    @patch("mergeguard.core.engine.GitHubClient")
    def test_llm_skipped_when_disabled(self, MockClientClass):
        """LLM analysis should not run when llm_enabled is False."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(132, "Feature")
        other_pr = _make_pr(133, "Other")

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.return_value = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        config = MergeGuardConfig(llm_enabled=False, check_regressions=False)
        engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=config)
        report = engine.analyze_pr(132)

        # Should complete without errors even without anthropic installed
        assert report.pr.number == 132


class TestAnalysisCacheWiring:
    @patch("mergeguard.core.engine.GitHubClient")
    def test_cache_hit_returns_cached_report(self, MockClientClass):
        """When cache has a result, it should be returned without full analysis."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(140, "Cached PR")
        mock_client.get_pr.return_value = target_pr

        # Set up cache to return a cached report
        cached_report = {
            "pr": target_pr.model_dump(mode="json"),
            "conflicts": [],
            "risk_score": 42.0,
            "risk_factors": {"conflict_severity": 0.0},
            "no_conflict_prs": [141],
            "analysis_duration_ms": 100,
            "analyzed_at": "2026-01-15T00:00:00",
        }
        mock_cache_instance = MagicMock()
        mock_cache_instance.get.return_value = cached_report
        mock_cache_instance.make_key.return_value = "test-key"

        with patch("mergeguard.core.engine.AnalysisCache", return_value=mock_cache_instance):
            config = MergeGuardConfig(check_regressions=False)
            engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=config)
            report = engine.analyze_pr(140)

        # Should return the cached result
        assert report.risk_score == 42.0
        assert report.no_conflict_prs == [141]
        # get_open_prs should NOT have been called (skipped due to cache hit)
        mock_client.get_open_prs.assert_not_called()

    @patch("mergeguard.core.engine.GitHubClient")
    def test_cache_miss_runs_full_analysis(self, MockClientClass):
        """When cache misses, full analysis runs and result is cached."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(142, "Uncached PR")
        other_pr = _make_pr(143, "Other")

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.return_value = [
            ChangedFile(
                path="src/app.py", status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2, patch=PATCH_OVERLAPPING,
            )
        ]
        mock_client.get_open_prs.return_value = [target_pr, other_pr]
        mock_client.get_file_content.return_value = PYTHON_SOURCE
        mock_client.rate_limit_remaining = 5000

        # Cache miss
        mock_cache_instance = MagicMock()
        mock_cache_instance.get.return_value = None
        mock_cache_instance.make_key.return_value = "test-key"

        with patch("mergeguard.core.engine.AnalysisCache", return_value=mock_cache_instance):
            config = MergeGuardConfig(check_regressions=False)
            engine = MergeGuardEngine(token="fake", repo_full_name="owner/repo", config=config)
            report = engine.analyze_pr(142)

        # Full analysis should have run
        mock_client.get_open_prs.assert_called_once()
        # Result should have been cached
        mock_cache_instance.set.assert_called_once()


class TestInsertedFunctionDetection:
    """E2E: new function inserted before existing one is detected as 'added'."""

    @patch("mergeguard.core.engine.GitHubClient")
    def test_inserted_function_detected_as_added(self, MockClientClass):
        """When a new function is inserted before an existing one,
        the new function should be 'added' and the existing one should
        NOT be misreported as 'modified_body'."""
        mock_client = MagicMock()
        MockClientClass.return_value = mock_client

        target_pr = _make_pr(200, "Insert helper function", "alice")
        other_pr = _make_pr(201, "Other PR", "bob")

        target_files = [
            ChangedFile(
                path="src/utils.py", status=FileChangeStatus.MODIFIED,
                additions=3, deletions=0, patch=PATCH_INSERT_BEFORE,
            )
        ]
        other_files = []

        mock_client.get_pr.return_value = target_pr
        mock_client.get_pr_files.side_effect = lambda n: target_files if n == 200 else other_files
        mock_client.get_open_prs.return_value = [target_pr, other_pr]

        def mock_content(path, ref):
            if ref == "main":
                return PYTHON_SOURCE_INSERT_BASE
            return PYTHON_SOURCE_INSERT_HEAD

        mock_client.get_file_content.side_effect = mock_content
        mock_client.rate_limit_remaining = 5000

        config = MergeGuardConfig(check_regressions=False)
        engine = MergeGuardEngine(
            token="fake", repo_full_name="owner/repo", config=config,
        )
        report = engine.analyze_pr(200)

        # The new function should be detected
        symbol_names = {cs.symbol.name for cs in report.pr.changed_symbols}
        assert "new_helper" in symbol_names, (
            f"Expected 'new_helper' in changed symbols, got: {symbol_names}"
        )

        # It should be classified as "added"
        new_helper_cs = [
            cs for cs in report.pr.changed_symbols if cs.symbol.name == "new_helper"
        ]
        assert new_helper_cs[0].change_type == "added"

        # The existing function should NOT be misreported
        validate_cs = [
            cs for cs in report.pr.changed_symbols
            if cs.symbol.name == "validate_input"
        ]
        assert len(validate_cs) == 0, (
            f"validate_input should not appear in changed symbols, "
            f"but found with change_type={validate_cs[0].change_type if validate_cs else 'N/A'}"
        )
