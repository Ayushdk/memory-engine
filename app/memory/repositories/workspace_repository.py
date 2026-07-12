"""Workspace repository — one row per project, plus archive snapshots."""

import json
import sqlite3
from datetime import datetime

from app.models.domain.workspace import Workspace, WorkspaceArchive
from app.utils.ids import new_ulid
from app.utils.time import utc_now


class WorkspaceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, project_id: str) -> Workspace:
        """The project's workspace; a pristine empty one if none exists yet."""
        row = self._conn.execute(
            "SELECT * FROM workspaces WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return Workspace(project_id=project_id)
        return Workspace(
            project_id=row["project_id"],
            internal_summary=row["internal_summary"],
            transfer_summary=row["transfer_summary"],
            goal=row["goal"],
            blockers=json.loads(row["blockers_json"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def save(self, workspace: Workspace) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO workspaces "
                "(project_id, internal_summary, transfer_summary, goal, blockers_json, "
                "updated_at) VALUES (?,?,?,?,?,?)",
                (
                    workspace.project_id,
                    workspace.internal_summary,
                    workspace.transfer_summary,
                    workspace.goal,
                    json.dumps(workspace.blockers),
                    utc_now().isoformat(),
                ),
            )

    def reset(self, project_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM workspaces WHERE project_id = ?", (project_id,))

    def archive(self, project_id: str) -> str | None:
        """Snapshot the workspace into the archive, then reset. Returns the
        archive id, or None when there was nothing worth archiving."""
        workspace = self.get(project_id)
        if workspace.is_empty:
            return None
        archive_id = "wsa_" + new_ulid()
        with self._conn:
            self._conn.execute(
                "INSERT INTO workspace_archives "
                "(id, project_id, internal_summary, transfer_summary, goal, blockers_json, "
                "archived_at) VALUES (?,?,?,?,?,?,?)",
                (
                    archive_id,
                    project_id,
                    workspace.internal_summary,
                    workspace.transfer_summary,
                    workspace.goal,
                    json.dumps(workspace.blockers),
                    utc_now().isoformat(),
                ),
            )
            self._conn.execute("DELETE FROM workspaces WHERE project_id = ?", (project_id,))
        return archive_id

    def list_archives(self, project_id: str, limit: int = 20) -> list[WorkspaceArchive]:
        rows = self._conn.execute(
            "SELECT * FROM workspace_archives WHERE project_id = ? "
            "ORDER BY archived_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [
            WorkspaceArchive(
                id=r["id"],
                project_id=r["project_id"],
                internal_summary=r["internal_summary"],
                transfer_summary=r["transfer_summary"],
                goal=r["goal"],
                blockers=json.loads(r["blockers_json"]),
                archived_at=datetime.fromisoformat(r["archived_at"]),
            )
            for r in rows
        ]
