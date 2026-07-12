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
    # 3 — project state: versioned, synthesized snapshots of a project's
    # active knowledge (intelligence-layer.md §7). Never overwritten.
    """
    CREATE TABLE IF NOT EXISTS project_states (
        id                  TEXT PRIMARY KEY,
        project_id          TEXT NOT NULL,
        version             INTEGER NOT NULL,
        content             TEXT NOT NULL,
        generated_from_json TEXT NOT NULL DEFAULT '[]',
        created_at          TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_project_states_project
        ON project_states (project_id, version DESC);
    """,
    # 4 — reinforcement count: how many times a memory has been re-observed
    # (bumped on every MemoryRepository.touch()). Gates Personal Brain
    # promotion (intelligence-layer.md §7.1) alongside confidence.
    """
    ALTER TABLE memories ADD COLUMN reinforcement_count INTEGER NOT NULL DEFAULT 0;
    """,
    # 5 — raw messages: append-only ledger of every ingested message, never
    # deleted. Episodes summarize a window of these and mark them summarized;
    # the row itself always survives (full-conversation compression pipeline).
    """
    CREATE TABLE IF NOT EXISTS raw_messages (
        id           TEXT PRIMARY KEY,
        session_id   TEXT NOT NULL,
        project_id   TEXT,
        platform     TEXT NOT NULL DEFAULT 'unknown',
        role         TEXT NOT NULL,
        content      TEXT NOT NULL,
        timestamp    TEXT NOT NULL,
        summarized   INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_raw_messages_session
        ON raw_messages (session_id, summarized, timestamp);
    """,
    # 6 — conversation summaries: one evolving "Current Context Summary" per
    # session, chained forward on every summarization. This is the canonical
    # conversation state injected on Sync — separate from workspace/project
    # knowledge, which stays project-scoped.
    """
    CREATE TABLE IF NOT EXISTS conversation_summaries (
        session_id  TEXT PRIMARY KEY,
        summary     TEXT NOT NULL DEFAULT '',
        updated_at  TEXT NOT NULL
    );
    """,
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
        with conn:
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {number}")
