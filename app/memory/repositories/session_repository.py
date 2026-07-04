"""Session repository — tracks which conversations are (recently) active."""

import sqlite3
from datetime import datetime

from app.models.domain.session import Session
from app.utils.time import utc_now


def _from_row(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        platform=row["platform"],
        project_id=row["project_id"],
        started_at=datetime.fromisoformat(row["started_at"]),
        last_activity_at=datetime.fromisoformat(row["last_activity_at"] or row["started_at"]),
    )


class SessionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def touch(self, session_id: str, platform: str, project_id: str | None = None) -> None:
        """Create the session on first sight; bump last_activity_at after.
        A later non-null project_id wins (the user picked a project mid-session)."""
        now = utc_now().isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT INTO sessions (id, platform, project_id, started_at, last_activity_at) "
                "VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "last_activity_at = excluded.last_activity_at, "
                "project_id = COALESCE(excluded.project_id, sessions.project_id)",
                (session_id, platform, project_id, now, now),
            )

    def get(self, session_id: str) -> Session | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def list_active(self, since: datetime) -> list[Session]:
        """Sessions with activity after `since`, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE COALESCE(last_activity_at, started_at) > ? "
            "ORDER BY COALESCE(last_activity_at, started_at) DESC, rowid DESC",
            (since.isoformat(),),
        ).fetchall()
        return [_from_row(r) for r in rows]
