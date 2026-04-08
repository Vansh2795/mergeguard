"""Tests for the DecisionsLog SQLite persistence class."""

from __future__ import annotations

from datetime import datetime

import pytest

from mergeguard.models import Decision, DecisionsEntry, DecisionType
from mergeguard.storage.decisions_log import DecisionsLog


def _make_entry(
    pr_number: int = 1,
    title: str = "Remove old API",
    author: str = "alice",
    merged_at: datetime | None = None,
    decisions: list[Decision] | None = None,
) -> DecisionsEntry:
    if merged_at is None:
        merged_at = datetime(2026, 1, 10)
    if decisions is None:
        decisions = [
            Decision(
                decision_type=DecisionType.REMOVAL,
                entity="old_function",
                file_path="src/api.py",
                description="Removed deprecated old_function",
                pr_number=pr_number,
                merged_at=merged_at,
                author=author,
            )
        ]
    return DecisionsEntry(
        pr_number=pr_number,
        title=title,
        merged_at=merged_at,
        author=author,
        decisions=decisions,
    )


class TestRecordAndRetrieve:
    """record_merge + get_recent_decisions round-trip."""

    def test_record_and_get_recent_decisions(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            entry = _make_entry(pr_number=42, author="bob")
            db.record_merge(entry)

            results = db.get_recent_decisions()

            assert len(results) == 1
            d = results[0]
            assert d.pr_number == 42
            assert d.author == "bob"
            assert d.decision_type == DecisionType.REMOVAL
            assert d.entity == "old_function"
            assert d.file_path == "src/api.py"
        finally:
            db.close()

    def test_multiple_decisions_in_one_entry(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            merged_at = datetime(2026, 2, 1)
            decisions = [
                Decision(
                    decision_type=DecisionType.REMOVAL,
                    entity="func_a",
                    file_path="src/a.py",
                    description="Removed func_a",
                    pr_number=10,
                    merged_at=merged_at,
                    author="carol",
                ),
                Decision(
                    decision_type=DecisionType.MIGRATION,
                    entity="legacy_module",
                    file_path="src/legacy.py",
                    description="Migrated legacy_module",
                    pr_number=10,
                    merged_at=merged_at,
                    author="carol",
                ),
            ]
            entry = DecisionsEntry(
                pr_number=10,
                title="Cleanup PR",
                merged_at=merged_at,
                author="carol",
                decisions=decisions,
            )
            db.record_merge(entry)

            results = db.get_recent_decisions()
            assert len(results) == 2
        finally:
            db.close()


class TestEmptyDatabase:
    """Empty database returns empty lists."""

    def test_get_recent_decisions_empty(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            results = db.get_recent_decisions()
            assert results == []
        finally:
            db.close()

    def test_find_regressions_empty(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            regressions = db.find_regressions(["some_symbol"], ["some/file.py"])
            assert regressions == []
        finally:
            db.close()


class TestFindRegressions:
    """find_regressions detects re-added removed symbols and modified migrated files."""

    def test_detects_re_added_removed_symbol(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            entry = _make_entry(
                pr_number=5,
                decisions=[
                    Decision(
                        decision_type=DecisionType.REMOVAL,
                        entity="deprecated_helper",
                        file_path="src/utils.py",
                        description="Removed deprecated_helper",
                        pr_number=5,
                        merged_at=datetime(2026, 1, 5),
                        author="dev",
                    )
                ],
            )
            db.record_merge(entry)

            # New PR adds back deprecated_helper
            regressions = db.find_regressions(
                pr_symbols=["deprecated_helper", "some_new_func"],
                pr_files=["src/utils.py"],
            )

            assert len(regressions) == 1
            assert regressions[0].entity == "deprecated_helper"
            assert regressions[0].decision_type == DecisionType.REMOVAL
        finally:
            db.close()

    def test_no_regression_when_symbol_not_in_pr(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            entry = _make_entry(
                pr_number=7,
                decisions=[
                    Decision(
                        decision_type=DecisionType.REMOVAL,
                        entity="removed_func",
                        file_path="src/old.py",
                        description="Removed",
                        pr_number=7,
                        merged_at=datetime(2026, 1, 7),
                        author="dev",
                    )
                ],
            )
            db.record_merge(entry)

            regressions = db.find_regressions(
                pr_symbols=["unrelated_func"],
                pr_files=["src/new.py"],
            )
            assert regressions == []
        finally:
            db.close()

    def test_detects_modified_migrated_file(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            entry = _make_entry(
                pr_number=8,
                decisions=[
                    Decision(
                        decision_type=DecisionType.MIGRATION,
                        entity="old_pattern",
                        file_path="src/legacy.py",
                        description="Migrated away from legacy.py",
                        pr_number=8,
                        merged_at=datetime(2026, 1, 8),
                        author="dev",
                    )
                ],
            )
            db.record_merge(entry)

            # New PR modifies the migrated file
            regressions = db.find_regressions(
                pr_symbols=[],
                pr_files=["src/legacy.py", "src/other.py"],
            )

            assert len(regressions) == 1
            assert regressions[0].decision_type == DecisionType.MIGRATION
            assert regressions[0].file_path == "src/legacy.py"
        finally:
            db.close()

    def test_migration_without_file_path_not_matched(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            merged_at = datetime(2026, 1, 9)
            entry = DecisionsEntry(
                pr_number=9,
                title="Migration",
                merged_at=merged_at,
                author="dev",
                decisions=[
                    Decision(
                        decision_type=DecisionType.MIGRATION,
                        entity="some_pattern",
                        file_path=None,  # No file path
                        description="Migrated pattern",
                        pr_number=9,
                        merged_at=merged_at,
                        author="dev",
                    )
                ],
            )
            db.record_merge(entry)

            regressions = db.find_regressions(
                pr_symbols=["some_pattern"],
                pr_files=["any/file.py"],
            )
            # MIGRATION with no file_path should not be flagged
            assert regressions == []
        finally:
            db.close()


class TestLimitParameter:
    """limit parameter on get_recent_decisions is respected."""

    def test_limit_restricts_results(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            for i in range(10):
                entry = _make_entry(
                    pr_number=100 + i,
                    merged_at=datetime(2026, 1, i + 1),
                    decisions=[
                        Decision(
                            decision_type=DecisionType.REMOVAL,
                            entity=f"func_{i}",
                            file_path="src/module.py",
                            description=f"Removed func_{i}",
                            pr_number=100 + i,
                            merged_at=datetime(2026, 1, i + 1),
                            author="dev",
                        )
                    ],
                )
                db.record_merge(entry)

            results = db.get_recent_decisions(limit=3)
            assert len(results) == 3
        finally:
            db.close()

    def test_limit_one_returns_most_recent(self, tmp_path):
        db = DecisionsLog(tmp_path / "decisions.db")
        try:
            for i, date in enumerate(
                [datetime(2026, 1, 1), datetime(2026, 3, 1), datetime(2026, 2, 1)]
            ):
                entry = _make_entry(
                    pr_number=200 + i,
                    merged_at=date,
                    decisions=[
                        Decision(
                            decision_type=DecisionType.REMOVAL,
                            entity=f"entity_{i}",
                            file_path="src/x.py",
                            description="desc",
                            pr_number=200 + i,
                            merged_at=date,
                            author="dev",
                        )
                    ],
                )
                db.record_merge(entry)

            results = db.get_recent_decisions(limit=1)
            assert len(results) == 1
            # Most recent merged_at is 2026-03-01
            assert results[0].merged_at == datetime(2026, 3, 1)
        finally:
            db.close()


class TestContextManager:
    """Context manager works correctly."""

    def test_context_manager_basic(self, tmp_path):
        with DecisionsLog(tmp_path / "cm_test.db") as dl:
            entry = _make_entry(pr_number=99)
            dl.record_merge(entry)
            results = dl.get_recent_decisions()
            assert len(results) == 1

    def test_context_manager_closes_connection(self, tmp_path):
        db_path = tmp_path / "cm_close.db"
        with DecisionsLog(db_path) as dl:
            dl.record_merge(_make_entry(pr_number=55))

        # After context exit, the connection should be closed;
        # any attempt to query should raise an error
        with pytest.raises(Exception):
            dl.get_recent_decisions()
