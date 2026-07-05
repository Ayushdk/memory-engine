"""SQLite connection factory. WAL mode, one connection shared per process.

ponytail: single connection guarded by sqlite3's own serialization is enough
for a single-user local engine; switch to a pool if concurrency ever matters.
"""

import sqlite3
from pathlib import Path

from app.core.paths import SQLITE_DB_PATH
from app.memory.sqlite.schema import SCHEMA


def create_connection(db_path: Path | str = SQLITE_DB_PATH) -> sqlite3.Connection:
    """Open (and initialize) the database. Safe to call on an existing db."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    # ponytail: migration-lite for pre-release dev DBs created before these
    # columns existed; CREATE IF NOT EXISTS won't add them. Real migration
    # tooling is explicitly out of V1 (architecture.md §9).
    for column in ("project_id TEXT", "last_activity_at TEXT", "title TEXT"):
        try:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {column}")
        except sqlite3.OperationalError:
            pass  # column already exists
    return conn
