"""Raw message repository — the append-only conversation ledger.

Rows survive forever once processed (complete history always survives).
The single exception is `delete_unsummarized`: an explicit user "discard
this capture" from the extension may remove messages that have NOT yet been
folded into the rolling Current Context Summary — anything already
summarized is immutable. `mark_summarized_by_ids` is the only other
mutation (app.jobs.conversation_summary_jobs).
"""

import sqlite3
from datetime import datetime

from app.models.domain.raw_message import RawMessage


def _from_row(row: sqlite3.Row) -> RawMessage:
    return RawMessage(
        id=row["id"],
        session_id=row["session_id"],
        project_id=row["project_id"],
        platform=row["platform"],
        role=row["role"],
        content=row["content"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        summarized=bool(row["summarized"]),
    )


class RawMessageRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Exposed so a caller can wrap this write with another repository's
        write in one transaction (see conversation_summary_jobs)."""
        return self._conn

    def append(
        self,
        session_id: str,
        role: str,
        content: str,
        project_id: str | None = None,
        platform: str = "unknown",
        timestamp: datetime | None = None,
    ) -> RawMessage:
        message = RawMessage(
            session_id=session_id,
            project_id=project_id,
            platform=platform,
            role=role,
            content=content,
            **({"timestamp": timestamp} if timestamp else {}),
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO raw_messages "
                "(id, session_id, project_id, platform, role, content, timestamp, summarized) "
                "VALUES (?,?,?,?,?,?,?,0)",
                (
                    message.id,
                    message.session_id,
                    message.project_id,
                    message.platform,
                    message.role,
                    message.content,
                    message.timestamp.isoformat(),
                ),
            )
        return message

    def unsummarized(self, session_id: str) -> list[RawMessage]:
        """Messages not yet folded into the rolling Current Context Summary,
        oldest first — exactly what the next chain step needs to consume."""
        rows = self._conn.execute(
            "SELECT * FROM raw_messages WHERE session_id = ? AND summarized = 0 "
            "ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [_from_row(r) for r in rows]

    def mark_summarized_by_ids(self, ids: list[str], commit: bool = True) -> None:
        """Flag exactly these messages as folded in — id-based so a message
        appended mid-summarization is never marked before it's consumed."""
        if not ids:
            return
        sql = "UPDATE raw_messages SET summarized = 1 WHERE id = ?"
        args = [(i,) for i in ids]
        if commit:
            with self._conn:
                self._conn.executemany(sql, args)
        else:
            # Caller owns the transaction (paired with another repository's
            # write, e.g. conversation_summary_jobs saving the summary).
            self._conn.executemany(sql, args)

    def delete_unsummarized(self, session_id: str) -> int:
        """User-invoked capture discard: drop the session's messages that no
        summary has consumed yet. Summarized rows are never touched."""
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM raw_messages WHERE session_id = ? AND summarized = 0",
                (session_id,),
            )
        return cursor.rowcount

    def list(self, session_id: str) -> list[RawMessage]:
        rows = self._conn.execute(
            "SELECT * FROM raw_messages WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [_from_row(r) for r in rows]
