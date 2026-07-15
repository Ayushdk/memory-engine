"""Unified memory repository — the only code that reads/writes the memories table."""

from __future__ import annotations  # the `list` method shadows builtin list in annotations

import json
import sqlite3
from datetime import datetime

from app.models.domain.memory import Memory
from app.models.enums import Confidence, MemoryCategory, MemoryStatus, MemoryView
from app.utils.time import utc_now

_CONFIDENCE_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}

_COLUMNS = (
    "id, content, summary, category, view, project_id, importance, confidence, "
    "status, supersedes, source_json, tags_json, created_at, updated_at, "
    "last_accessed_at, access_count, reinforcement_count"
)


def _to_row(m: Memory) -> tuple:
    return (
        m.id,
        m.content,
        m.summary,
        m.category.value,
        m.view.value,
        m.project_id,
        m.importance,
        m.confidence.value,
        m.status.value,
        m.supersedes,
        m.source.model_dump_json() if m.source else None,
        json.dumps(m.tags),
        m.created_at.isoformat(),
        m.updated_at.isoformat(),
        m.last_accessed_at.isoformat() if m.last_accessed_at else None,
        m.access_count,
        m.reinforcement_count,
    )


def _from_row(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        content=row["content"],
        summary=row["summary"],
        category=row["category"],
        view=row["view"],
        project_id=row["project_id"],
        importance=row["importance"],
        confidence=row["confidence"],
        status=row["status"],
        supersedes=row["supersedes"],
        source=json.loads(row["source_json"]) if row["source_json"] else None,
        tags=json.loads(row["tags_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_accessed_at=(
            datetime.fromisoformat(row["last_accessed_at"]) if row["last_accessed_at"] else None
        ),
        access_count=row["access_count"],
        reinforcement_count=row["reinforcement_count"],
    )


class MemoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, memory: Memory) -> None:
        """Insert or replace (upsert keyed on id)."""
        placeholders = ", ".join("?" * 17)
        with self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO memories ({_COLUMNS}) VALUES ({placeholders})",
                _to_row(memory),
            )

    def get(self, memory_id: str) -> Memory | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def list(
        self,
        view: MemoryView | None = None,
        project_id: str | None = None,
        category: MemoryCategory | None = None,
        status: MemoryStatus | None = MemoryStatus.ACTIVE,
        limit: int | None = None,
    ) -> list[Memory]:
        clauses, params = [], []
        for column, value in (
            ("view", view),
            ("project_id", project_id),
            ("category", category),
            ("status", status),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value.value if hasattr(value, "value") else value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        suffix = ""
        if limit is not None:
            suffix = " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM memories {where} ORDER BY id{suffix}", params
        ).fetchall()
        return [_from_row(r) for r in rows]

    def set_status(self, memory_id: str, status: MemoryStatus) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE memories SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, utc_now().isoformat(), memory_id),
            )

    def record_access(self, memory_ids: list[str]) -> None:
        """Retrieval Engine bookkeeping: bump access stats for returned memories."""
        now = utc_now().isoformat()
        with self._conn:
            self._conn.executemany(
                "UPDATE memories SET last_accessed_at = ?, access_count = access_count + 1 "
                "WHERE id = ?",
                [(now, mid) for mid in memory_ids],
            )

    def touch(self, memory_id: str, confidence: Confidence | None = None) -> None:
        """Reinforcement: recency bump, plus a confidence upgrade if the new
        observation is more confident (never downgrades) — decision #5,
        "same knowledge re-extracted bumps confidence/recency, no duplicate"."""
        now = utc_now().isoformat()
        if confidence is not None:
            existing = self.get(memory_id)
            if existing and _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[existing.confidence]:
                with self._conn:
                    self._conn.execute(
                        "UPDATE memories SET updated_at = ?, confidence = ?, "
                        "reinforcement_count = reinforcement_count + 1 WHERE id = ?",
                        (now, confidence.value, memory_id),
                    )
                return
        with self._conn:
            self._conn.execute(
                "UPDATE memories SET updated_at = ?, reinforcement_count = reinforcement_count + 1 "
                "WHERE id = ?",
                (now, memory_id),
            )

    def delete(self, memory_id: str) -> bool:
        """Hard delete — the user's right to forget."""
        with self._conn:
            cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            if cur.rowcount > 0:
                self._conn.execute(
                    "DELETE FROM memory_relations WHERE from_id = ? OR to_id = ?",
                    (memory_id, memory_id),
                )
        return cur.rowcount > 0
