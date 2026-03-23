"""SQLite-backed store for DORA metrics snapshots."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from mergeguard.models import MetricsSnapshot


class MetricsStore:
    """Persistent store for conflict metrics snapshots.

    Uses the same SQLite database as DecisionsLog (decisions.db) to keep
    all persistent state in one place.
    """

    def __init__(self, db_path: str | Path = ".mergeguard-cache/decisions.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pr_number INTEGER NOT NULL,
                repo TEXT NOT NULL,
                analyzed_at TEXT NOT NULL,
                risk_score REAL NOT NULL,
                conflict_count INTEGER NOT NULL,
                severity_max TEXT NOT NULL DEFAULT 'none',
                resolved_at TEXT,
                resolution_type TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_repo_analyzed
            ON metrics_snapshots(repo, analyzed_at DESC)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_pr_repo
            ON metrics_snapshots(pr_number, repo)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_unresolved
            ON metrics_snapshots(repo) WHERE resolved_at IS NULL
        """)
        self._conn.commit()

    def record_snapshot(self, snapshot: MetricsSnapshot) -> None:
        """Upsert a metrics snapshot — updates existing unresolved entry or inserts new."""
        # Try to update an existing unresolved entry for this PR+repo
        cursor = self._conn.execute(
            """UPDATE metrics_snapshots
               SET analyzed_at = ?, risk_score = ?, conflict_count = ?, severity_max = ?
               WHERE pr_number = ? AND repo = ? AND resolved_at IS NULL""",
            (
                snapshot.analyzed_at.isoformat(),
                snapshot.risk_score,
                snapshot.conflict_count,
                snapshot.severity_max,
                snapshot.pr_number,
                snapshot.repo,
            ),
        )
        if cursor.rowcount == 0:
            # No existing unresolved entry — insert new
            self._conn.execute(
                """INSERT INTO metrics_snapshots
                   (pr_number, repo, analyzed_at, risk_score, conflict_count,
                    severity_max, resolved_at, resolution_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.pr_number,
                    snapshot.repo,
                    snapshot.analyzed_at.isoformat(),
                    snapshot.risk_score,
                    snapshot.conflict_count,
                    snapshot.severity_max,
                    snapshot.resolved_at.isoformat() if snapshot.resolved_at else None,
                    snapshot.resolution_type,
                ),
            )
        self._conn.commit()

    def resolve_pr(
        self,
        pr_number: int,
        repo: str,
        resolved_at: datetime,
        resolution_type: str,
    ) -> int:
        """Mark all unresolved snapshots for a PR as resolved. Returns rows affected."""
        cursor = self._conn.execute(
            """UPDATE metrics_snapshots
               SET resolved_at = ?, resolution_type = ?
               WHERE pr_number = ? AND repo = ? AND resolved_at IS NULL""",
            (resolved_at.isoformat(), resolution_type, pr_number, repo),
        )
        self._conn.commit()
        return cursor.rowcount

    def get_snapshots(
        self,
        repo: str,
        since: datetime,
        until: datetime | None = None,
    ) -> list[MetricsSnapshot]:
        """Fetch snapshots in a time window."""
        if until is not None:
            cursor = self._conn.execute(
                """SELECT pr_number, repo, analyzed_at, risk_score, conflict_count,
                          severity_max, resolved_at, resolution_type
                   FROM metrics_snapshots
                   WHERE repo = ? AND analyzed_at >= ? AND analyzed_at <= ?
                   ORDER BY analyzed_at DESC""",
                (repo, since.isoformat(), until.isoformat()),
            )
        else:
            cursor = self._conn.execute(
                """SELECT pr_number, repo, analyzed_at, risk_score, conflict_count,
                          severity_max, resolved_at, resolution_type
                   FROM metrics_snapshots
                   WHERE repo = ? AND analyzed_at >= ?
                   ORDER BY analyzed_at DESC""",
                (repo, since.isoformat()),
            )
        return [self._row_to_snapshot(row) for row in cursor]

    def get_unresolved(self, repo: str) -> list[MetricsSnapshot]:
        """Get all currently unresolved conflict snapshots."""
        cursor = self._conn.execute(
            """SELECT pr_number, repo, analyzed_at, risk_score, conflict_count,
                      severity_max, resolved_at, resolution_type
               FROM metrics_snapshots
               WHERE repo = ? AND resolved_at IS NULL
               ORDER BY analyzed_at DESC""",
            (repo,),
        )
        return [self._row_to_snapshot(row) for row in cursor]

    def get_merge_count(self, repo: str, since: datetime) -> int:
        """Count distinct merged PRs since a given date."""
        cursor = self._conn.execute(
            """SELECT COUNT(DISTINCT pr_number)
               FROM metrics_snapshots
               WHERE repo = ? AND resolved_at >= ? AND resolution_type = 'merged'""",
            (repo, since.isoformat()),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def prune(self, retention_days: int) -> int:
        """Delete resolved entries older than retention_days. Returns rows deleted."""
        cursor = self._conn.execute(
            """DELETE FROM metrics_snapshots
               WHERE resolved_at IS NOT NULL
               AND julianday('now') - julianday(resolved_at) > ?""",
            (retention_days,),
        )
        self._conn.commit()
        return cursor.rowcount

    @staticmethod
    def _row_to_snapshot(row: tuple[Any, ...]) -> MetricsSnapshot:
        return MetricsSnapshot(
            pr_number=row[0],
            repo=row[1],
            analyzed_at=datetime.fromisoformat(row[2]),
            risk_score=row[3],
            conflict_count=row[4],
            severity_max=row[5],
            resolved_at=datetime.fromisoformat(row[6]) if row[6] else None,
            resolution_type=row[7],
        )

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
