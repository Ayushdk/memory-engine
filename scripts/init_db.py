"""Create data dirs and the SQLite schema. Idempotent."""

from app.core.paths import SQLITE_DB_PATH, ensure_data_dirs
from app.memory.sqlite.connection import create_connection

if __name__ == "__main__":
    ensure_data_dirs()
    create_connection().close()
    print(f"Initialized {SQLITE_DB_PATH}")
