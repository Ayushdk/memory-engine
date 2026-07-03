"""Memory administration — the user's right to forget (architecture.md §6).

Same dual-store discipline as ingestion, in reverse: SQLite (truth) first,
Chroma (index) second. A Chroma failure after a successful SQLite delete
leaves only a stale index entry, repairable by reset_db.py.
"""

from dataclasses import dataclass
from typing import Literal

from loguru import logger

from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.vector.chroma_client import ChromaVectorStore


@dataclass(frozen=True)
class DeletionResult:
    memory_id: str
    found: bool
    success: bool
    synchronization_status: Literal["in_sync", "sqlite_only", "failed", "not_found"]
    reasoning: str | None = None


class MemoryAdmin:
    def __init__(self, repository: MemoryRepository, vector_store: ChromaVectorStore) -> None:
        self._repository = repository
        self._vector_store = vector_store

    def delete(self, memory_id: str) -> DeletionResult:
        # SQLite FIRST; if it fails, Chroma is never touched.
        try:
            found = self._repository.delete(memory_id)
        except Exception as exc:
            logger.error("SQLite delete failed for {}: {}", memory_id, exc)
            return DeletionResult(
                memory_id=memory_id,
                found=True,
                success=False,
                synchronization_status="failed",
                reasoning=f"sqlite delete failed: {exc}",
            )

        if not found:
            return DeletionResult(
                memory_id=memory_id,
                found=False,
                success=False,
                synchronization_status="not_found",
            )

        try:
            self._vector_store.delete(memory_id)
        except Exception as exc:
            logger.warning("Chroma delete failed for {} (run reset_db.py): {}", memory_id, exc)
            return DeletionResult(
                memory_id=memory_id,
                found=True,
                success=True,
                synchronization_status="sqlite_only",
                reasoning="deleted from SQLite; index entry is stale until reset_db.py",
            )

        return DeletionResult(
            memory_id=memory_id, found=True, success=True, synchronization_status="in_sync"
        )
