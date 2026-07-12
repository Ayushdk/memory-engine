"""Project State repository — versioned, append-only (intelligence-layer.md
§7). Never UPDATE or DELETE a version; a new reflection cycle appends one.
"""

import json
import sqlite3
from datetime import datetime

from app.models.domain.project_state import ProjectState
from app.utils.time import utc_now


def _from_row(row: sqlite3.Row) -> ProjectState:
    return ProjectState(
        id=row["id"],
        project_id=row["project_id"],
        version=row["version"],
        content=row["content"],
        generated_from=json.loads(row["generated_from_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class ProjectStateRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def latest(self, project_id: str) -> ProjectState | None:
        row = self._conn.execute(
            "SELECT * FROM project_states WHERE project_id = ? ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return _from_row(row) if row else None

    def list_versions(self, project_id: str, limit: int = 20) -> list[ProjectState]:
        rows = self._conn.execute(
            "SELECT * FROM project_states WHERE project_id = ? ORDER BY version DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [_from_row(r) for r in rows]

    def save(self, project_id: str, content: str, generated_from: list[str]) -> ProjectState:
        """Append the next version for this project."""
        prior = self.latest(project_id)
        state = ProjectState(
            project_id=project_id,
            version=(prior.version + 1 if prior else 1),
            content=content,
            generated_from=generated_from,
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO project_states "
                "(id, project_id, version, content, generated_from_json, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    state.id,
                    state.project_id,
                    state.version,
                    state.content,
                    json.dumps(state.generated_from),
                    utc_now().isoformat(),
                ),
            )
        return state
