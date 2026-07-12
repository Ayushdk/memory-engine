"""Additive-only SQLite migrations via PRAGMA user_version.

Each entry runs exactly once, in order, on every database (fresh or old);
`user_version` records how many have been applied. Rules: additive only
(new tables, new columns, new indexes) — never destructive; scripts must be
safe on a database that already contains data.
"""

import sqlite3

MIGRATIONS: list[str] = [
    # 1 — episodes: first-class conversation segments (intelligence-layer.md §4)
    """
    CREATE TABLE IF NOT EXISTS episodes (
        id               TEXT PRIMARY KEY,
        session_id       TEXT NOT NULL,
        project_id       TEXT,
        platform         TEXT,
        status           TEXT NOT NULL DEFAULT 'open',
        boundary_reason  TEXT,
        message_count    INTEGER NOT NULL DEFAULT 0,
        started_at       TEXT NOT NULL,
        ended_at         TEXT,
        summary_internal TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes (session_id, status);
    CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes (project_id, status);
    """,
    # 2 — workspace: current working state per project (intelligence-layer.md
    # §3.3). Timeline is NOT stored here — it derives from the episodes table.
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        project_id       TEXT PRIMARY KEY,
        internal_summary TEXT NOT NULL DEFAULT '',
        transfer_summary TEXT NOT NULL DEFAULT '',
        goal             TEXT,
        blockers_json    TEXT NOT NULL DEFAULT '[]',
        updated_at       TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS workspace_archives (
        id               TEXT PRIMARY KEY,
        project_id       TEXT NOT NULL,
        internal_summary TEXT NOT NULL,
        transfer_summary TEXT NOT NULL,
        goal             TEXT,
        blockers_json    TEXT NOT NULL,
        archived_at      TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_workspace_archives_project
        ON workspace_archives (project_id, archived_at);
    """,
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
        with conn:
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {number}")
