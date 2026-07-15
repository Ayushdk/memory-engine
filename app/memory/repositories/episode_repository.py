"""Episode repository — owns episode rows and their open→closed→summarized
lifecycle. Deterministic; boundary *policy* lives in the EpisodeTracker."""

import sqlite3
from datetime import datetime

from app.models.domain.episode import Episode
from app.utils.time import utc_now


def _from_row(row: sqlite3.Row) -> Episode:
    return Episode(
        id=row["id"],
        session_id=row["session_id"],
        project_id=row["project_id"],
        platform=row["platform"],
        status=row["status"],
        boundary_reason=row["boundary_reason"],
        message_count=row["message_count"],
        started_at=datetime.fromisoformat(row["started_at"]),
        ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
        summary_internal=row["summary_internal"],
    )


class EpisodeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, episode_id: str) -> Episode | None:
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def get_open(self, session_id: str) -> Episode | None:
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE session_id = ? AND status = 'open' "
            "ORDER BY started_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return _from_row(row) if row else None

    def open_for(
        self,
        session_id: str,
        project_id: str | None,
        platform: str | None,
        started_at: datetime | None = None,
    ) -> Episode:
        """The session's open episode, created if none exists. Later non-null
        project_id wins (project picked mid-conversation). `started_at` should
        be the triggering message's timestamp — it defines the evidence window,
        and stamping 'now' would exclude the very message that opened it."""
        existing = self.get_open(session_id)
        if existing:
            if project_id and existing.project_id != project_id:
                with self._conn:
                    self._conn.execute(
                        "UPDATE episodes SET project_id = ? WHERE id = ?",
                        (project_id, existing.id),
                    )
                existing = existing.model_copy(update={"project_id": project_id})
            return existing
        episode = Episode(
            session_id=session_id,
            project_id=project_id,
            platform=platform,
            **({"started_at": started_at} if started_at else {}),
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO episodes (id, session_id, project_id, platform, status, "
                "message_count, started_at) VALUES (?,?,?,?,?,?,?)",
                (
                    episode.id,
                    episode.session_id,
                    episode.project_id,
                    episode.platform,
                    episode.status,
                    episode.message_count,
                    episode.started_at.isoformat(),
                ),
            )
        return episode

    def record_message(self, episode_id: str) -> int:
        """Increment the message count; returns the new count."""
        with self._conn:
            self._conn.execute(
                "UPDATE episodes SET message_count = message_count + 1 WHERE id = ?",
                (episode_id,),
            )
        return self._conn.execute(
            "SELECT message_count FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()[0]

    def close(self, episode_id: str, reason: str) -> Episode | None:
        """open → closed with the boundary reason; no-op if already closed."""
        with self._conn:
            updated = self._conn.execute(
                "UPDATE episodes SET status = 'closed', boundary_reason = ?, "
                "ended_at = ? WHERE id = ? AND status = 'open'",
                (reason, utc_now().isoformat(), episode_id),
            ).rowcount
        return self.get(episode_id) if updated else None

    def delete_open(self, session_id: str) -> str | None:
        """User-invoked capture discard: drop the session's OPEN episode so it
        never reaches summarization. Closed/summarized episodes are history
        and are never deleted. Returns the discarded episode id, if any."""
        episode = self.get_open(session_id)
        if episode is None:
            return None
        with self._conn:
            self._conn.execute("DELETE FROM episodes WHERE id = ? AND status = 'open'", (episode.id,))
        return episode.id

    def set_summary(self, episode_id: str, summary: str) -> None:
        """closed → summarized."""
        with self._conn:
            self._conn.execute(
                "UPDATE episodes SET summary_internal = ?, status = 'summarized' "
                "WHERE id = ?",
                (summary, episode_id),
            )

    def list_open_inactive(self, cutoff: datetime) -> list[Episode]:
        """Open episodes whose session has been quiet since before `cutoff`."""
        rows = self._conn.execute(
            "SELECT e.* FROM episodes e JOIN sessions s ON s.id = e.session_id "
            "WHERE e.status = 'open' "
            "AND COALESCE(s.last_activity_at, s.started_at) < ?",
            (cutoff.isoformat(),),
        ).fetchall()
        return [_from_row(r) for r in rows]

    def list(
        self,
        session_id: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[Episode]:
        query = "SELECT * FROM episodes WHERE 1=1"
        params: list = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        return [_from_row(r) for r in self._conn.execute(query, params).fetchall()]
