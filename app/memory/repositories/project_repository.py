"""Project repository — id, name, status, consolidated state_json."""

import json
import sqlite3
from datetime import datetime

from app.models.domain.project import Project


def _from_row(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        state=json.loads(row["state_json"]) if row["state_json"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class ProjectRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, project: Project) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO projects "
                "(id, name, status, state_json, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (
                    project.id,
                    project.name,
                    project.status.value,
                    json.dumps(project.state) if project.state is not None else None,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )

    def get(self, project_id: str) -> Project | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def list(self) -> list[Project]:
        rows = self._conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [_from_row(r) for r in rows]
