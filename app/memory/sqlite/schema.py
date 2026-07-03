"""SQLite DDL — source of truth (architecture.md §5). All six tables land in
Phase 1 so later phases never need migrations."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id               TEXT PRIMARY KEY,
    content          TEXT NOT NULL,
    summary          TEXT,
    category         TEXT NOT NULL,
    view             TEXT NOT NULL,
    project_id       TEXT,
    importance       INTEGER NOT NULL,
    confidence       TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active',
    supersedes       TEXT,
    source_json      TEXT,
    tags_json        TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    last_accessed_at TEXT,
    access_count     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_memories_view_project
    ON memories (view, project_id, status);

CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active',
    state_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    platform   TEXT NOT NULL,
    started_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS working_memory (
    session_id    TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS injections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    memory_id   TEXT NOT NULL,
    injected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_injections_session ON injections (session_id);

CREATE TABLE IF NOT EXISTS memory_relations (
    from_id    TEXT NOT NULL,
    to_id      TEXT NOT NULL,
    relation   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id, relation)
);
"""
