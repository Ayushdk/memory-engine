"""PRAGMA user_version migrations: fresh, legacy, and idempotent paths."""

import sqlite3

from app.memory.sqlite.connection import create_connection
from app.memory.sqlite.migrations import MIGRATIONS, apply_migrations
from app.memory.sqlite.schema import SCHEMA


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def user_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def test_fresh_database_is_fully_migrated(tmp_path):
    conn = create_connection(tmp_path / "fresh.db")
    assert user_version(conn) == len(MIGRATIONS)
    assert "episodes" in table_names(conn)
    conn.close()


def test_migrations_are_idempotent(tmp_path):
    conn = create_connection(tmp_path / "twice.db")
    apply_migrations(conn)  # second run: nothing to do, no error
    assert user_version(conn) == len(MIGRATIONS)
    conn.close()


def test_legacy_database_upgrades_in_place(tmp_path):
    # A pre-migration database: V1 schema, user_version 0, existing data.
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(SCHEMA)
    legacy.execute(
        "INSERT INTO sessions (id, platform, started_at) VALUES ('s1', 'chatgpt', '2026-01-01')"
    )
    legacy.commit()
    legacy.close()

    conn = create_connection(path)
    assert user_version(conn) == len(MIGRATIONS)
    assert "episodes" in table_names(conn)
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1  # data intact
    conn.close()
