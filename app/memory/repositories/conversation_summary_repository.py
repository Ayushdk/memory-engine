"""Conversation summary repository — one row per session, replaced in place."""

import sqlite3
from datetime import datetime

from app.models.domain.conversation_summary import ConversationSummary
from app.utils.time import utc_now


class ConversationSummaryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Exposed so a caller can wrap this write with another repository's
        write in one transaction (see conversation_summary_jobs)."""
        return self._conn

    def get(self, session_id: str) -> ConversationSummary:
        """The session's rolling summary; a pristine empty one if none yet."""
        row = self._conn.execute(
            "SELECT * FROM conversation_summaries WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return ConversationSummary(session_id=session_id)
        return ConversationSummary(
            session_id=row["session_id"],
            summary=row["summary"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def latest_other(self, exclude_session_id: str, since: datetime) -> ConversationSummary | None:
        """Most recently updated non-empty summary from a DIFFERENT session,
        no older than `since` — cross-AI handoff: a brand-new chat has no
        summary of its own yet, so Sync there carries forward whatever the
        user was just doing elsewhere instead of coming up empty."""
        row = self._conn.execute(
            "SELECT * FROM conversation_summaries "
            "WHERE session_id != ? AND summary != '' AND updated_at >= ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (exclude_session_id, since.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return ConversationSummary(
            session_id=row["session_id"],
            summary=row["summary"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def save(self, summary: ConversationSummary, commit: bool = True) -> None:
        sql = (
            "INSERT OR REPLACE INTO conversation_summaries (session_id, summary, updated_at) "
            "VALUES (?,?,?)"
        )
        args = (summary.session_id, summary.summary, utc_now().isoformat())
        if commit:
            with self._conn:
                self._conn.execute(sql, args)
        else:
            # Caller owns the transaction (e.g. an atomic write paired with
            # another repository's — see RawMessageRepository.conn usage).
            self._conn.execute(sql, args)
