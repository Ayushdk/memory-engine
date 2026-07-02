"""Filesystem layout. All data lives under the project-local data/ directory."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
SQLITE_DIR = DATA_DIR / "sqlite"
CHROMA_DIR = DATA_DIR / "chroma"

SQLITE_DB_PATH = SQLITE_DIR / "openmemory.db"


def ensure_data_dirs() -> None:
    for path in (SQLITE_DIR, CHROMA_DIR):
        path.mkdir(parents=True, exist_ok=True)
