"""Tests for regression detection module."""
from __future__ import annotations

from datetime import datetime

from mergeguard.core.regression import detect_regressions
from mergeguard.models import (
    ChangedFile,
    ChangedSymbol,
    ConflictType,
    Decision,
    DecisionsEntry,
    DecisionType,
    FileChangeStatus,
    PRInfo,
    Symbol,
    SymbolType,
)
from mergeguard.storage.decisions_log import DecisionsLog


def _make_pr(number: int, changed_symbols=None, changed_files=None) -> PRInfo:
    pr = PRInfo(
        number=number,
        title=f"PR {number}",
        author="dev",
        base_branch="main",
        head_branch=f"feature/{number}",
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    if changed_symbols:
        pr.changed_symbols = changed_symbols
    if changed_files:
        pr.changed_files = changed_files
    return pr


def _make_changed_symbol(name: str, file_path: str = "src/app.py") -> ChangedSymbol:
    return ChangedSymbol(
        symbol=Symbol(
            name=name,
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            start_line=1,
            end_line=10,
        ),
        change_type="modified_body",
        diff_lines=(1, 10),
    )


class TestDetectRegressions:
    def test_detect_removal_regression(self, tmp_path):
        """PR re-introduces a symbol that was deliberately removed."""
        log = DecisionsLog(db_path=tmp_path / "decisions.db")
        log.record_merge(
            DecisionsEntry(
                pr_number=40,
                title="Remove legacy handler",
                merged_at=datetime(2026, 1, 10),
                author="carol",
                decisions=[
                    Decision(
                        decision_type=DecisionType.REMOVAL,
                        entity="legacy_auth_handler",
                        file_path="src/auth/legacy.py",
                        description="Removed legacy auth handler in favor of JWT",
                        pr_number=40,
                        merged_at=datetime(2026, 1, 10),
                        author="carol",
                    )
                ],
            )
        )

        pr = _make_pr(
            50,
            changed_symbols=[_make_changed_symbol("legacy_auth_handler", "src/auth/legacy.py")],
            changed_files=[ChangedFile(path="src/auth/legacy.py", status=FileChangeStatus.MODIFIED)],
        )

        regressions = detect_regressions(pr, log)
        assert len(regressions) == 1
        assert regressions[0].conflict_type == ConflictType.REGRESSION
        assert regressions[0].symbol_name == "legacy_auth_handler"
        assert regressions[0].target_pr == 40
        log.close()

    def test_detect_migration_regression(self, tmp_path):
        """PR modifies a file that had a migration decision."""
        log = DecisionsLog(db_path=tmp_path / "decisions.db")
        log.record_merge(
            DecisionsEntry(
                pr_number=35,
                title="Migrate to new ORM",
                merged_at=datetime(2026, 1, 8),
                author="dave",
                decisions=[
                    Decision(
                        decision_type=DecisionType.MIGRATION,
                        entity="sqlalchemy_models",
                        file_path="src/db/models.py",
                        description="Migrated from SQLAlchemy to Tortoise ORM",
                        pr_number=35,
                        merged_at=datetime(2026, 1, 8),
                        author="dave",
                    )
                ],
            )
        )

        pr = _make_pr(
            51,
            changed_files=[ChangedFile(path="src/db/models.py", status=FileChangeStatus.MODIFIED)],
        )

        regressions = detect_regressions(pr, log)
        assert len(regressions) == 1
        assert regressions[0].conflict_type == ConflictType.REGRESSION
        assert regressions[0].target_pr == 35
        log.close()

    def test_no_regressions(self, tmp_path):
        """PR doesn't overlap with any decisions in the log."""
        log = DecisionsLog(db_path=tmp_path / "decisions.db")
        log.record_merge(
            DecisionsEntry(
                pr_number=30,
                title="Remove old util",
                merged_at=datetime(2026, 1, 5),
                author="eve",
                decisions=[
                    Decision(
                        decision_type=DecisionType.REMOVAL,
                        entity="old_utility_func",
                        file_path="src/utils/old.py",
                        description="Removed unused utility function",
                        pr_number=30,
                        merged_at=datetime(2026, 1, 5),
                        author="eve",
                    )
                ],
            )
        )

        pr = _make_pr(
            52,
            changed_symbols=[_make_changed_symbol("new_feature", "src/features/new.py")],
            changed_files=[ChangedFile(path="src/features/new.py", status=FileChangeStatus.ADDED)],
        )

        regressions = detect_regressions(pr, log)
        assert len(regressions) == 0
        log.close()
