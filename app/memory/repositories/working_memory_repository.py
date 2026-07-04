"""Working-memory snapshots — the session buffer that survives restarts (§5)."""

import json
import sqlite3
from datetime import datetime

from app.models.domain.session import ConversationMessage
from app.utils.time import utc_now


def _serialize(messages: list[ConversationMessage]) -> str:
    return json.dumps(
        [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
            for m in messages
        ]
    )


def _deserialize(snapshot_json: str) -> list[ConversationMessage]:
    return [
        ConversationMessage(
            role=item["role"],
            content=item["content"],
            timestamp=datetime.fromisoformat(item["timestamp"]),
        )
        for item in json.loads(snapshot_json)
    ]


class WorkingMemoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_snapshot(self, session_id: str, messages: list[ConversationMessage]) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO working_memory (session_id, snapshot_json, updated_at) "
                "VALUES (?,?,?)",
                (session_id, _serialize(messages), utc_now().isoformat()),
            )

    def load(self, session_id: str) -> list[ConversationMessage]:
        row = self._conn.execute(
            "SELECT snapshot_json FROM working_memory WHERE session_id = ?", (session_id,)
        ).fetchone()
        return _deserialize(row["snapshot_json"]) if row else []

    def load_all(self) -> dict[str, list[ConversationMessage]]:
        rows = self._conn.execute(
            "SELECT session_id, snapshot_json FROM working_memory"
        ).fetchall()
        return {r["session_id"]: _deserialize(r["snapshot_json"]) for r in rows}

    def delete(self, session_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM working_memory WHERE session_id = ?", (session_id,))
