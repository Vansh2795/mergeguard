"""Tests for conflict detection module."""

from __future__ import annotations

from datetime import datetime

from conftest import make_test_pr

from mergeguard.core.conflict import (
    FileOverlap,
    _get_modified_ranges,
    _is_comment_only_change,
    _is_test_file,
    classify_conflicts,
    compute_file_overlaps,
)
from mergeguard.models import (
    ChangedFile,
    ChangedSymbol,
    ConflictSeverity,
    ConflictType,
    FileChangeStatus,
    PRInfo,
    Symbol,
    SymbolType,
)


class TestComputeFileOverlaps:
    def test_no_overlap(self):
        pr_a = make_test_pr(1, ["a.py", "b.py"])
        pr_b = make_test_pr(2, ["c.py", "d.py"])
        overlaps = compute_file_overlaps(pr_a, [pr_b])
        assert len(overlaps) == 0

    def test_single_file_overlap(self):
        pr_a = make_test_pr(1, ["a.py", "shared.py"])
        pr_b = make_test_pr(2, ["shared.py", "c.py"])
        overlaps = compute_file_overlaps(pr_a, [pr_b])
        assert 2 in overlaps
        assert len(overlaps[2]) == 1
        assert overlaps[2][0].file_path == "shared.py"

    def test_skip_same_pr(self):
        pr = make_test_pr(1, ["a.py"])
        overlaps = compute_file_overlaps(pr, [pr])
        assert len(overlaps) == 0

    def test_multiple_overlaps(self):
        pr_a = make_test_pr(1, ["a.py", "b.py", "c.py"])
        pr_b = make_test_pr(2, ["a.py", "b.py", "d.py"])
        overlaps = compute_file_overlaps(pr_a, [pr_b])
        assert len(overlaps[2]) == 2


class TestFileOverlap:
    def test_has_line_overlap_true(self):
        overlap = FileOverlap(
            file_path="f.py",
            pr_a=1,
            pr_b=2,
            pr_a_lines=[(10, 20)],
            pr_b_lines=[(15, 25)],
        )
        assert overlap.has_line_overlap is True

    def test_has_line_overlap_false(self):
        overlap = FileOverlap(
            file_path="f.py",
            pr_a=1,
            pr_b=2,
            pr_a_lines=[(10, 20)],
            pr_b_lines=[(25, 35)],
        )
        assert overlap.has_line_overlap is False

    def test_has_line_overlap_adjacent(self):
        overlap = FileOverlap(
            file_path="f.py",
            pr_a=1,
            pr_b=2,
            pr_a_lines=[(10, 20)],
            pr_b_lines=[(20, 25)],
        )
        assert overlap.has_line_overlap is True


class TestDuplicationConflicts:
    """Tests for _check_duplication_conflicts via classify_conflicts."""

    def _make_symbol(self, name, file_path="src/utils.py", signature=None):
        return Symbol(
            name=name,
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            start_line=1,
            end_line=10,
            signature=signature,
        )

    def _make_changed_symbol(self, name, file_path="src/utils.py", signature=None):
        return ChangedSymbol(
            symbol=self._make_symbol(name, file_path, signature),
            change_type="added",
            diff_lines=(1, 10),
        )

    def test_duplication_detected_for_similar_symbols(self):
        """Two PRs adding similarly-named functions should trigger duplication."""
        sym_a = self._make_changed_symbol(
            "process_user_data", signature="def process_user_data(user, data)"
        )
        sym_b = self._make_changed_symbol(
            "process_user_data",
            file_path="src/handler.py",
            signature="def process_user_data(user, data)",
        )
        pr_a = make_test_pr(1, ["src/utils.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/handler.py"], symbols=[sym_b])

        # No file overlap needed — duplication is symbol-level
        overlaps = [
            FileOverlap(
                file_path="src/shared.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 5)],
                pr_b_lines=[(50, 55)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        dup_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DUPLICATION]
        assert len(dup_conflicts) >= 1
        assert dup_conflicts[0].severity == ConflictSeverity.INFO

    def test_no_duplication_for_unrelated_symbols(self):
        """Unrelated symbol names should not trigger duplication."""
        sym_a = self._make_changed_symbol(
            "authenticate_user", signature="def authenticate_user(token)"
        )
        sym_b = self._make_changed_symbol(
            "send_email_notification",
            file_path="src/notifier.py",
            signature="def send_email_notification(to, subject, body)",
        )
        pr_a = make_test_pr(1, ["src/utils.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/notifier.py"], symbols=[sym_b])

        overlaps = [
            FileOverlap(
                file_path="src/shared.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 5)],
                pr_b_lines=[(50, 55)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        dup_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DUPLICATION]
        assert len(dup_conflicts) == 0

    def test_no_duplication_when_no_symbols(self):
        """No symbols means no duplication conflicts."""
        pr_a = make_test_pr(1, ["src/a.py"])
        pr_b = make_test_pr(2, ["src/b.py"])
        overlaps = [
            FileOverlap(
                file_path="src/shared.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 5)],
                pr_b_lines=[(50, 55)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        dup_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DUPLICATION]
        assert len(dup_conflicts) == 0


class TestGetModifiedRanges:
    def _make_symbol(self, name, file_path, start, end, diff_lines):
        return ChangedSymbol(
            symbol=Symbol(
                name=name,
                symbol_type=SymbolType.FUNCTION,
                file_path=file_path,
                start_line=start,
                end_line=end,
            ),
            change_type="modified_body",
            diff_lines=diff_lines,
        )

    def test_get_modified_ranges_multiple_symbols(self):
        """When multiple symbols are changed in the same file, all ranges should be returned."""
        sym_a = self._make_symbol("func_a", "shared.py", 1, 10, (1, 10))
        sym_b = self._make_symbol("func_b", "shared.py", 20, 30, (20, 30))
        pr = make_test_pr(1, ["shared.py"], symbols=[sym_a, sym_b])

        ranges = _get_modified_ranges(pr, "shared.py")
        assert len(ranges) == 2
        assert (1, 10) in ranges
        assert (20, 30) in ranges

    def test_get_modified_ranges_single_symbol(self):
        """Single symbol should still return its range."""
        sym = self._make_symbol("func_a", "file.py", 5, 15, (5, 15))
        pr = make_test_pr(1, ["file.py"], symbols=[sym])

        ranges = _get_modified_ranges(pr, "file.py")
        assert ranges == [(5, 15)]

    def test_get_modified_ranges_no_symbols(self):
        """No matching symbols should fall back to raw diff data."""
        pr = make_test_pr(1, ["other.py"])
        ranges = _get_modified_ranges(pr, "other.py")
        # No patch data either, so empty
        assert ranges == []


class TestIsTestFile:
    """Tests for _is_test_file()."""

    # Python patterns
    def test_python_test_prefix(self):
        assert _is_test_file("test_utils.py") is True

    def test_python_test_suffix(self):
        assert _is_test_file("utils_test.py") is True

    def test_python_tests_directory(self):
        assert _is_test_file("tests/unit/test_engine.py") is True

    def test_python_test_directory(self):
        assert _is_test_file("test/test_engine.py") is True

    # JS/TS patterns
    def test_js_test_file(self):
        assert _is_test_file("src/utils.test.js") is True

    def test_ts_spec_file(self):
        assert _is_test_file("src/utils.spec.ts") is True

    def test_jest_directory(self):
        assert _is_test_file("__tests__/utils.js") is True

    # Go patterns
    def test_go_test_file(self):
        assert _is_test_file("pkg/handler_test.go") is True

    # Ruby patterns
    def test_ruby_spec_directory(self):
        assert _is_test_file("spec/models/user_spec.rb") is True

    # False positives
    def test_contest_not_test(self):
        assert _is_test_file("src/contest.py") is False

    def test_testimony_not_test(self):
        assert _is_test_file("src/testimony.py") is False

    def test_source_file(self):
        assert _is_test_file("src/mergeguard/core/engine.py") is False

    def test_nested_source_file(self):
        assert _is_test_file("src/utils/helpers.py") is False


class TestTestFileSeverityDowngrade:
    """Tests that test-file conflicts get downgraded severity."""

    def _make_symbol(self, name, file_path, start=1, end=10):
        return Symbol(
            name=name,
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            start_line=start,
            end_line=end,
        )

    def _make_changed_symbol(self, name, file_path, start=1, end=10, diff_lines=None):
        return ChangedSymbol(
            symbol=self._make_symbol(name, file_path, start, end),
            change_type="modified_body",
            diff_lines=diff_lines or (start, end),
        )

    def test_hard_shared_symbols_source_critical(self):
        """Hard conflict with shared symbols in source file -> CRITICAL."""
        sym_a = self._make_changed_symbol("func", "src/core.py")
        sym_b = self._make_changed_symbol("func", "src/core.py")
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(5, 15)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        hard = [c for c in conflicts if c.conflict_type == ConflictType.HARD]
        assert len(hard) >= 1
        assert hard[0].severity == ConflictSeverity.CRITICAL

    def test_hard_shared_symbols_test_warning(self):
        """Hard conflict with shared symbols in test file -> WARNING (downgraded from CRITICAL)."""
        sym_a = self._make_changed_symbol("test_func", "tests/test_core.py")
        sym_b = self._make_changed_symbol("test_func", "tests/test_core.py")
        pr_a = make_test_pr(1, ["tests/test_core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["tests/test_core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="tests/test_core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(5, 15)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        hard = [c for c in conflicts if c.conflict_type == ConflictType.HARD]
        assert len(hard) >= 1
        assert hard[0].severity == ConflictSeverity.WARNING

    def test_hard_no_symbols_source_warning(self):
        """Hard conflict without shared symbols in source file -> WARNING."""
        pr_a = make_test_pr(1, ["src/core.py"])
        pr_b = make_test_pr(2, ["src/core.py"])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(5, 15)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        hard = [c for c in conflicts if c.conflict_type == ConflictType.HARD]
        assert len(hard) == 1
        assert hard[0].severity == ConflictSeverity.WARNING

    def test_hard_no_symbols_test_info(self):
        """Hard conflict without shared symbols in test file -> INFO (downgraded from WARNING)."""
        pr_a = make_test_pr(1, ["tests/test_core.py"])
        pr_b = make_test_pr(2, ["tests/test_core.py"])
        overlaps = [
            FileOverlap(
                file_path="tests/test_core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(5, 15)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        hard = [c for c in conflicts if c.conflict_type == ConflictType.HARD]
        assert len(hard) == 1
        assert hard[0].severity == ConflictSeverity.INFO
        assert "append new tests" in hard[0].description
        assert "rebasing after merge" in hard[0].recommendation

    def test_behavioral_source_warning(self):
        """Behavioral conflict in source file -> WARNING."""
        sym_a = self._make_changed_symbol(
            "func", "src/core.py", start=1, end=10, diff_lines=(1, 10)
        )
        sym_b = self._make_changed_symbol(
            "func", "src/core.py", start=20, end=30, diff_lines=(20, 30)
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        behavioral = [c for c in conflicts if c.conflict_type == ConflictType.BEHAVIORAL]
        assert len(behavioral) >= 1
        assert behavioral[0].severity == ConflictSeverity.WARNING

    def test_behavioral_test_info(self):
        """Behavioral conflict in test file -> INFO (downgraded from WARNING)."""
        sym_a = self._make_changed_symbol(
            "test_func", "tests/test_core.py", start=1, end=10, diff_lines=(1, 10)
        )
        sym_b = self._make_changed_symbol(
            "test_func", "tests/test_core.py", start=20, end=30, diff_lines=(20, 30)
        )
        pr_a = make_test_pr(1, ["tests/test_core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["tests/test_core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="tests/test_core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        behavioral = [c for c in conflicts if c.conflict_type == ConflictType.BEHAVIORAL]
        assert len(behavioral) >= 1
        assert behavioral[0].severity == ConflictSeverity.INFO


class TestCallerCalleeBehavioralConflict:
    """Tests for caller/callee behavioral conflict detection."""

    def _make_symbol(self, name, file_path, start=1, end=10, deps=None):
        return Symbol(
            name=name,
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            start_line=start,
            end_line=end,
            dependencies=deps or [],
        )

    def _make_changed_symbol(
        self,
        name,
        file_path,
        start=1,
        end=10,
        diff_lines=None,
        deps=None,
        change_type="modified_body",
    ):
        return ChangedSymbol(
            symbol=self._make_symbol(name, file_path, start, end, deps),
            change_type=change_type,
            diff_lines=diff_lines or (start, end),
        )

    def test_caller_callee_detected(self):
        """PR A modifies foo, PR B modifies bar, foo calls bar → WARNING."""
        sym_a = self._make_changed_symbol(
            "foo",
            "src/core.py",
            start=1,
            end=10,
            diff_lines=(1, 10),
            deps=["bar"],
        )
        sym_b = self._make_changed_symbol(
            "bar",
            "src/core.py",
            start=20,
            end=30,
            diff_lines=(20, 30),
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        behavioral = [c for c in conflicts if c.conflict_type == ConflictType.BEHAVIORAL]
        assert len(behavioral) >= 1
        cc = [c for c in behavioral if "\u2192" in (c.symbol_name or "")]
        assert len(cc) == 1
        assert cc[0].severity == ConflictSeverity.INFO

    def test_caller_callee_signature_change_keeps_warning(self):
        """Callee has modified_signature -> stays WARNING."""
        sym_a = self._make_changed_symbol(
            "foo",
            "src/core.py",
            start=1,
            end=10,
            diff_lines=(1, 10),
            deps=["bar"],
        )
        sym_b = self._make_changed_symbol(
            "bar",
            "src/core.py",
            start=20,
            end=30,
            diff_lines=(20, 30),
            change_type="modified_signature",
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        cc = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and "\u2192" in (c.symbol_name or "")
        ]
        assert len(cc) == 1
        assert cc[0].severity == ConflictSeverity.WARNING

    def test_caller_callee_test_file(self):
        """Same scenario in test file → INFO."""
        sym_a = self._make_changed_symbol(
            "test_foo",
            "tests/test_core.py",
            start=1,
            end=10,
            diff_lines=(1, 10),
            deps=["test_bar"],
        )
        sym_b = self._make_changed_symbol(
            "test_bar",
            "tests/test_core.py",
            start=20,
            end=30,
            diff_lines=(20, 30),
        )
        pr_a = make_test_pr(1, ["tests/test_core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["tests/test_core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="tests/test_core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        cc = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and "\u2192" in (c.symbol_name or "")
        ]
        assert len(cc) == 1
        assert cc[0].severity == ConflictSeverity.INFO

    def test_no_relationship(self):
        """Different functions, no call relationship → no caller/callee conflict."""
        sym_a = self._make_changed_symbol(
            "foo",
            "src/core.py",
            start=1,
            end=10,
            diff_lines=(1, 10),
            deps=[],
        )
        sym_b = self._make_changed_symbol(
            "bar",
            "src/core.py",
            start=20,
            end=30,
            diff_lines=(20, 30),
            deps=[],
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        cc = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and "\u2192" in (c.symbol_name or "")
        ]
        assert len(cc) == 0

    def test_bidirectional(self):
        """A calls B AND B calls A → still one conflict (deduplicated)."""
        sym_a = self._make_changed_symbol(
            "foo",
            "src/core.py",
            start=1,
            end=10,
            diff_lines=(1, 10),
            deps=["bar"],
        )
        sym_b = self._make_changed_symbol(
            "bar",
            "src/core.py",
            start=20,
            end=30,
            diff_lines=(20, 30),
            deps=["foo"],
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        cc = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and "\u2192" in (c.symbol_name or "")
        ]
        assert len(cc) == 1


class TestPRDuplication:
    """Tests for PR-level duplication detection."""

    def test_similar_titles_with_file_overlap(self):
        """Same title, shared files → DUPLICATION WARNING."""
        pr_a = PRInfo(
            number=1,
            title="Fix login button styling",
            author="dev1",
            base_branch="main",
            head_branch="fix-login-1",
            head_sha="sha1",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        pr_a.changed_files = [
            ChangedFile(path="src/login.py", status=FileChangeStatus.MODIFIED),
        ]
        pr_b = PRInfo(
            number=2,
            title="Fix login button styling",
            author="dev2",
            base_branch="main",
            head_branch="fix-login-2",
            head_sha="sha2",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        pr_b.changed_files = [
            ChangedFile(path="src/login.py", status=FileChangeStatus.MODIFIED),
        ]
        overlaps = [
            FileOverlap(
                file_path="src/login.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(1, 10)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        dup = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.DUPLICATION
            and c.severity == ConflictSeverity.WARNING
        ]
        assert len(dup) >= 1

    def test_different_titles_no_duplication(self):
        """Unrelated titles → no PR-level duplication."""
        pr_a = PRInfo(
            number=1,
            title="Add user authentication",
            author="dev1",
            base_branch="main",
            head_branch="auth",
            head_sha="sha1",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        pr_a.changed_files = [
            ChangedFile(path="src/shared.py", status=FileChangeStatus.MODIFIED),
        ]
        pr_b = PRInfo(
            number=2,
            title="Upgrade database driver",
            author="dev2",
            base_branch="main",
            head_branch="db",
            head_sha="sha2",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        pr_b.changed_files = [
            ChangedFile(path="src/shared.py", status=FileChangeStatus.MODIFIED),
        ]
        overlaps = [
            FileOverlap(
                file_path="src/shared.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 5)],
                pr_b_lines=[(50, 55)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        pr_dup = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.DUPLICATION
            and c.severity == ConflictSeverity.WARNING
        ]
        assert len(pr_dup) == 0

    def test_similar_titles_no_file_overlap(self):
        """Similar titles but no shared files → no conflict."""
        from mergeguard.core.conflict import _check_pr_duplication

        pr_a = PRInfo(
            number=1,
            title="Fix login button",
            author="dev1",
            base_branch="main",
            head_branch="fix-1",
            head_sha="sha1",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        pr_a.changed_files = [
            ChangedFile(path="src/a.py", status=FileChangeStatus.MODIFIED),
        ]
        pr_b = PRInfo(
            number=2,
            title="Fix login button",
            author="dev2",
            base_branch="main",
            head_branch="fix-2",
            head_sha="sha2",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        pr_b.changed_files = [
            ChangedFile(path="src/b.py", status=FileChangeStatus.MODIFIED),
        ]
        conflicts: list = []
        _check_pr_duplication(pr_a, pr_b, [], conflicts)
        assert len(conflicts) == 0

    def test_description_boosts_similarity(self):
        """Mediocre title match + strong description match → detected."""
        pr_a = PRInfo(
            number=1,
            title="Update auth module",
            author="dev1",
            base_branch="main",
            head_branch="auth-1",
            head_sha="sha1",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            description=(
                "Refactor the authentication flow to use JWT tokens instead of session cookies"
            ),
        )
        pr_a.changed_files = [
            ChangedFile(path="src/auth.py", status=FileChangeStatus.MODIFIED),
        ]
        pr_b = PRInfo(
            number=2,
            title="Refactor auth module",
            author="dev2",
            base_branch="main",
            head_branch="auth-2",
            head_sha="sha2",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            description=(
                "Refactor the authentication flow to use JWT tokens instead of session cookies"
            ),
        )
        pr_b.changed_files = [
            ChangedFile(path="src/auth.py", status=FileChangeStatus.MODIFIED),
        ]
        overlaps = [
            FileOverlap(
                file_path="src/auth.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 50)],
                pr_b_lines=[(1, 50)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        pr_dup = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.DUPLICATION
            and c.severity == ConflictSeverity.WARNING
        ]
        assert len(pr_dup) >= 1


class TestSkipSameFileSameNameDuplication:
    """P0: Same-file same-name modifications should not trigger duplication."""

    def _make_changed_symbol(self, name, file_path, start=1, end=10, change_type="modified_body"):
        return ChangedSymbol(
            symbol=Symbol(
                name=name,
                symbol_type=SymbolType.FUNCTION,
                file_path=file_path,
                start_line=start,
                end_line=end,
                signature=f"def {name}(self)",
            ),
            change_type=change_type,
            diff_lines=(start, end),
        )

    def test_skip_same_file_same_name_duplication(self):
        """Two PRs modifying the same function in the same file should not trigger duplication."""
        sym_a = self._make_changed_symbol("_generate", "src/chat/base.py")
        sym_b = self._make_changed_symbol("_generate", "src/chat/base.py")
        pr_a = make_test_pr(1, ["src/chat/base.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/chat/base.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/chat/base.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 5)],
                pr_b_lines=[(6, 10)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        dup_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DUPLICATION]
        assert len(dup_conflicts) == 0

    def test_different_file_same_name_still_detected(self):
        """Same name in different files should still trigger duplication (when added)."""
        sym_a = self._make_changed_symbol("process_data", "src/a.py", change_type="added")
        sym_b = self._make_changed_symbol("process_data", "src/b.py", change_type="added")
        pr_a = make_test_pr(1, ["src/a.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/b.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/shared.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 5)],
                pr_b_lines=[(50, 55)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        dup_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DUPLICATION]
        assert len(dup_conflicts) >= 1

    def test_both_modified_body_skips_duplication(self):
        """Both sides modify existing code in different files -> no duplication."""
        sym_a = self._make_changed_symbol("_generate", "src/a.py", change_type="modified_body")
        sym_b = self._make_changed_symbol("_generate", "src/b.py", change_type="modified_body")
        pr_a = make_test_pr(1, ["src/a.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/b.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/shared.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 5)],
                pr_b_lines=[(50, 55)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        dup_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DUPLICATION]
        assert len(dup_conflicts) == 0

    def test_one_added_one_modified_still_detected(self):
        """One PR adds, the other modifies -> duplication still fires."""
        sym_a = self._make_changed_symbol("process_data", "src/a.py", change_type="added")
        sym_b = self._make_changed_symbol("process_data", "src/b.py", change_type="modified_body")
        pr_a = make_test_pr(1, ["src/a.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/b.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/shared.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 5)],
                pr_b_lines=[(50, 55)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        dup_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DUPLICATION]
        assert len(dup_conflicts) >= 1


class TestCommentOnlyChange:
    """P1: Comment/docstring-only changes should be skipped."""

    def _make_changed_symbol(self, name, file_path, raw_diff=None, start=1, end=10):
        return ChangedSymbol(
            symbol=Symbol(
                name=name,
                symbol_type=SymbolType.FUNCTION,
                file_path=file_path,
                start_line=start,
                end_line=end,
            ),
            change_type="modified_body",
            diff_lines=(start, end),
            raw_diff=raw_diff,
        )

    def test_is_comment_only_python(self):
        assert _is_comment_only_change("+# this is a comment\n+# another", "foo.py") is True

    def test_is_comment_only_python_docstring(self):
        assert _is_comment_only_change('+"""docstring"""', "foo.py") is True

    def test_is_comment_only_js(self):
        assert _is_comment_only_change("+// comment\n+// more", "foo.js") is True

    def test_mixed_comment_and_code(self):
        assert _is_comment_only_change("+# comment\n+x = 1", "foo.py") is False

    def test_none_raw_diff(self):
        assert _is_comment_only_change(None, "foo.py") is False

    def test_unknown_extension(self):
        assert _is_comment_only_change("+# comment", "foo.xyz") is False

    def test_context_lines_are_ignored(self):
        """Context lines (no +/- prefix) should not affect the result."""
        diff = (
            "@@ -1,5 +1,5 @@\n def hello():\n"
            "-    # old comment\n+    # new comment\n     return True\n"
        )
        assert _is_comment_only_change(diff, "main.py") is True

    def test_hunk_headers_are_ignored(self):
        diff = "@@ -1,3 +1,3 @@\n import os\n-# old\n+# new\n"
        assert _is_comment_only_change(diff, "main.py") is True

    def test_comment_only_change_skipped(self):
        """Both PRs change only comments → no behavioral conflict."""
        sym_a = self._make_changed_symbol(
            "func",
            "src/core.py",
            raw_diff="+# updated comment",
            start=1,
            end=10,
        )
        sym_b = self._make_changed_symbol(
            "func",
            "src/core.py",
            raw_diff="+# different comment",
            start=20,
            end=30,
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        behavioral = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and c.symbol_name == "func"
        ]
        assert len(behavioral) == 0

    def test_mixed_comment_and_code_not_skipped(self):
        """One PR changes comments, other changes code → conflict fires."""
        sym_a = self._make_changed_symbol(
            "func",
            "src/core.py",
            raw_diff="+# just a comment",
            start=1,
            end=10,
        )
        sym_b = self._make_changed_symbol(
            "func",
            "src/core.py",
            raw_diff="+x = compute()",
            start=20,
            end=30,
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(20, 30)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        behavioral = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and c.symbol_name == "func"
        ]
        assert len(behavioral) >= 1


class TestClassDemotion:
    """Class-level behavioral conflicts should always be demoted to INFO."""

    def _make_changed_symbol(
        self, name, file_path, sym_type=SymbolType.FUNCTION, start=1, end=10, diff_lines=None
    ):
        return ChangedSymbol(
            symbol=Symbol(
                name=name,
                symbol_type=sym_type,
                file_path=file_path,
                start_line=start,
                end_line=end,
            ),
            change_type="modified_body",
            diff_lines=diff_lines or (start, end),
        )

    def test_class_changes_always_info(self):
        """Any class symbol → INFO regardless of distance."""
        sym_a = self._make_changed_symbol(
            "MyClass",
            "src/core.py",
            sym_type=SymbolType.CLASS,
            start=1,
            end=500,
            diff_lines=(40, 50),
        )
        sym_b = self._make_changed_symbol(
            "MyClass",
            "src/core.py",
            sym_type=SymbolType.CLASS,
            start=1,
            end=500,
            diff_lines=(60, 70),
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(40, 50)],
                pr_b_lines=[(60, 70)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        behavioral = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and c.symbol_name == "MyClass"
        ]
        assert len(behavioral) == 1
        assert behavioral[0].severity == ConflictSeverity.INFO

    def test_non_class_symbols_unaffected(self):
        """Function symbol stays WARNING regardless of distance."""
        sym_a = self._make_changed_symbol(
            "my_func",
            "src/core.py",
            sym_type=SymbolType.FUNCTION,
            start=1,
            end=500,
            diff_lines=(10, 20),
        )
        sym_b = self._make_changed_symbol(
            "my_func",
            "src/core.py",
            sym_type=SymbolType.FUNCTION,
            start=1,
            end=500,
            diff_lines=(300, 310),
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(10, 20)],
                pr_b_lines=[(300, 310)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        behavioral = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and c.symbol_name == "my_func"
        ]
        assert len(behavioral) == 1
        assert behavioral[0].severity == ConflictSeverity.WARNING

    def test_method_in_shared_class_demoted_to_info(self):
        """Method whose parent class is also a shared symbol → INFO."""
        # Both PRs modify the class AND the method inside it
        cls_a = self._make_changed_symbol(
            "BaseChatModel",
            "src/core.py",
            sym_type=SymbolType.CLASS,
            start=1,
            end=500,
            diff_lines=(40, 50),
        )
        cls_b = self._make_changed_symbol(
            "BaseChatModel",
            "src/core.py",
            sym_type=SymbolType.CLASS,
            start=1,
            end=500,
            diff_lines=(60, 70),
        )
        method_a = ChangedSymbol(
            symbol=Symbol(
                name="_generate",
                symbol_type=SymbolType.METHOD,
                file_path="src/core.py",
                start_line=100,
                end_line=150,
                parent="BaseChatModel",
            ),
            change_type="modified_body",
            diff_lines=(110, 120),
        )
        method_b = ChangedSymbol(
            symbol=Symbol(
                name="_generate",
                symbol_type=SymbolType.METHOD,
                file_path="src/core.py",
                start_line=100,
                end_line=150,
                parent="BaseChatModel",
            ),
            change_type="modified_body",
            diff_lines=(130, 140),
        )
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[cls_a, method_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[cls_b, method_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(40, 50), (110, 120)],
                pr_b_lines=[(60, 70), (130, 140)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        method_conflicts = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and c.symbol_name == "_generate"
        ]
        assert len(method_conflicts) == 1
        assert method_conflicts[0].severity == ConflictSeverity.INFO

    def test_method_without_shared_class_stays_warning(self):
        """Method with parent class NOT in shared_symbols → stays WARNING."""
        method_a = ChangedSymbol(
            symbol=Symbol(
                name="_generate",
                symbol_type=SymbolType.METHOD,
                file_path="src/core.py",
                start_line=100,
                end_line=150,
                parent="BaseChatModel",
            ),
            change_type="modified_body",
            diff_lines=(110, 120),
        )
        method_b = ChangedSymbol(
            symbol=Symbol(
                name="_generate",
                symbol_type=SymbolType.METHOD,
                file_path="src/core.py",
                start_line=100,
                end_line=150,
                parent="BaseChatModel",
            ),
            change_type="modified_body",
            diff_lines=(130, 140),
        )
        # Only method is shared — class is NOT in either PR's symbols
        pr_a = make_test_pr(1, ["src/core.py"], symbols=[method_a])
        pr_b = make_test_pr(2, ["src/core.py"], symbols=[method_b])
        overlaps = [
            FileOverlap(
                file_path="src/core.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(110, 120)],
                pr_b_lines=[(130, 140)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        method_conflicts = [
            c
            for c in conflicts
            if c.conflict_type == ConflictType.BEHAVIORAL and c.symbol_name == "_generate"
        ]
        assert len(method_conflicts) == 1
        assert method_conflicts[0].severity == ConflictSeverity.WARNING


class TestConflictLinePopulation:
    """Verify source_lines/target_lines are populated on all conflict types."""

    def test_hard_conflict_with_symbols_has_lines(self):
        """HARD conflicts with shared symbols should have source/target lines from diff_lines."""
        sym_a = ChangedSymbol(
            symbol=Symbol(
                name="process",
                symbol_type=SymbolType.FUNCTION,
                file_path="app.py",
                start_line=10,
                end_line=30,
            ),
            change_type="modified_body",
            diff_lines=(15, 25),
        )
        sym_b = ChangedSymbol(
            symbol=Symbol(
                name="process",
                symbol_type=SymbolType.FUNCTION,
                file_path="app.py",
                start_line=10,
                end_line=30,
            ),
            change_type="modified_body",
            diff_lines=(18, 28),
        )
        pr_a = make_test_pr(1, ["app.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["app.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="app.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(15, 25)],
                pr_b_lines=[(18, 28)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        hard = [c for c in conflicts if c.conflict_type == ConflictType.HARD]
        assert len(hard) == 1
        assert hard[0].source_lines == (15, 25)
        assert hard[0].target_lines == (18, 28)

    def test_hard_conflict_file_level_has_lines(self):
        """File-level HARD conflicts (no shared symbols) use FileOverlap lines."""
        pr_a = make_test_pr(1, ["app.py"])
        pr_b = make_test_pr(2, ["app.py"])
        overlaps = [
            FileOverlap(
                file_path="app.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(1, 10)],
                pr_b_lines=[(5, 15)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        hard = [c for c in conflicts if c.conflict_type == ConflictType.HARD]
        assert len(hard) == 1
        assert hard[0].source_lines == (1, 10)
        assert hard[0].target_lines == (5, 15)

    def test_behavioral_conflict_has_lines(self):
        """BEHAVIORAL conflicts should have source/target lines from diff_lines."""
        sym_a = ChangedSymbol(
            symbol=Symbol(
                name="compute",
                symbol_type=SymbolType.FUNCTION,
                file_path="calc.py",
                start_line=1,
                end_line=20,
            ),
            change_type="modified_body",
            diff_lines=(5, 10),
        )
        sym_b = ChangedSymbol(
            symbol=Symbol(
                name="compute",
                symbol_type=SymbolType.FUNCTION,
                file_path="calc.py",
                start_line=1,
                end_line=20,
            ),
            change_type="modified_body",
            diff_lines=(15, 20),
        )
        pr_a = make_test_pr(1, ["calc.py"], symbols=[sym_a])
        pr_b = make_test_pr(2, ["calc.py"], symbols=[sym_b])
        overlaps = [
            FileOverlap(
                file_path="calc.py",
                pr_a=1,
                pr_b=2,
                pr_a_lines=[(5, 10)],
                pr_b_lines=[(15, 20)],
            )
        ]
        conflicts = classify_conflicts(pr_a, pr_b, overlaps)
        behavioral = [c for c in conflicts if c.conflict_type == ConflictType.BEHAVIORAL]
        assert len(behavioral) == 1
        assert behavioral[0].source_lines == (5, 10)
        assert behavioral[0].target_lines == (15, 20)

    def test_interface_conflict_has_lines(self):
        """INTERFACE conflicts should have source/target lines from symbol start/end."""
        sig_change = ChangedSymbol(
            symbol=Symbol(
                name="get_user",
                symbol_type=SymbolType.FUNCTION,
                file_path="users.py",
                start_line=10,
                end_line=25,
                signature="def get_user(user_id: int, include_email: bool = False) -> User",
            ),
            change_type="modified_signature",
            diff_lines=(10, 12),
        )
        caller = ChangedSymbol(
            symbol=Symbol(
                name="fetch_profile",
                symbol_type=SymbolType.FUNCTION,
                file_path="profile.py",
                start_line=40,
                end_line=55,
                dependencies=["get_user"],
            ),
            change_type="modified_body",
            diff_lines=(45, 50),
        )
        pr_a = make_test_pr(1, ["users.py"], symbols=[sig_change])
        pr_b = make_test_pr(2, ["profile.py"], symbols=[caller])
        conflicts = classify_conflicts(pr_a, pr_b, [])
        interface = [c for c in conflicts if c.conflict_type == ConflictType.INTERFACE]
        assert len(interface) == 1
        assert interface[0].source_lines == (10, 25)
        assert interface[0].target_lines == (40, 55)
