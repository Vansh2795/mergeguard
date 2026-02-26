"""SQLite-backed store for tracking merged PR decisions."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from mergeguard.models import Decision, DecisionsEntry, DecisionType


class DecisionsLog:
    """Persistent store for decisions extracted from merged PRs.

    Stored as a SQLite database (typically .mergeguard-cache/decisions.db)
    to survive across CI runs when using GitHub Actions cache.
    """

    def __init__(self, db_path: str | Path = ".mergeguard-cache/decisions.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pr_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                merged_at TEXT NOT NULL,
                author TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                entity TEXT NOT NULL,
                file_path TEXT,
                description TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_merged_at
            ON decisions(merged_at DESC)
        """)
        self._conn.commit()

    def record_merge(self, entry: DecisionsEntry) -> None:
        """Record decisions from a newly merged PR."""
        for decision in entry.decisions:
            self._conn.execute(
                """INSERT INTO decisions
                   (pr_number, title, merged_at, author, decision_type,
                    entity, file_path, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.pr_number,
                    entry.title,
                    entry.merged_at.isoformat(),
                    entry.author,
                    decision.decision_type.value,
                    decision.entity,
                    decision.file_path,
                    decision.description,
                ),
            )
        self._conn.commit()

    def get_recent_decisions(self, limit: int = 50) -> list[Decision]:
        """Retrieve the most recent decisions for regression checking."""
        cursor = self._conn.execute(
            """SELECT pr_number, merged_at, author, decision_type,
                      entity, file_path, description
               FROM decisions
               ORDER BY merged_at DESC
               LIMIT ?""",
            (limit,),
        )
        decisions: list[Decision] = []
        for row in cursor:
            decisions.append(
                Decision(
                    pr_number=row[0],
                    merged_at=datetime.fromisoformat(row[1]),
                    author=row[2],
                    decision_type=DecisionType(row[3]),
                    entity=row[4],
                    file_path=row[5],
                    description=row[6],
                )
            )
        return decisions

    def find_regressions(
        self, pr_symbols: list[str], pr_files: list[str]
    ) -> list[Decision]:
        """Check if the PR re-introduces something that was recently removed/changed.

        This compares the PR's symbols and files against recent REMOVAL and
        MIGRATION decisions.
        """
        recent = self.get_recent_decisions()
        regressions: list[Decision] = []

        for decision in recent:
            if decision.decision_type == DecisionType.REMOVAL:
                # Check if the PR adds back something that was removed
                if decision.entity in pr_symbols:
                    regressions.append(decision)

            elif decision.decision_type == DecisionType.MIGRATION:
                # Check if the PR uses the old pattern
                if decision.file_path and decision.file_path in pr_files:
                    regressions.append(decision)

        return regressions

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
