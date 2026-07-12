"""Memory relations — provenance links reflection leaves behind when it
merges or supersedes memories (e.g. "merged_from", "supersedes"). Read side
is for the Dashboard's future Timeline view; not needed until then.
"""

import sqlite3

from app.utils.time import utc_now


class MemoryRelationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def link(self, from_id: str, to_id: str, relation: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO memory_relations (from_id, to_id, relation, created_at) "
                "VALUES (?,?,?,?)",
                (from_id, to_id, relation, utc_now().isoformat()),
            )
