"""ChromaDB wrapper — embedding index only, always rebuildable from SQLite.

One collection `memories`: id = memory id, vector = MiniLM embedding,
metadata = {view, project_id, importance, status} for pre-filtering (§5).
"""

from pathlib import Path

import chromadb

from app.core.paths import CHROMA_DIR
from app.models.domain.memory import Memory

_COLLECTION = "memories"


def _metadata(memory: Memory) -> dict:
    meta = {
        "view": memory.view.value,
        "importance": memory.importance,
        "status": memory.status.value,
    }
    if memory.project_id:  # Chroma rejects None metadata values
        meta["project_id"] = memory.project_id
    return meta


class ChromaVectorStore:
    def __init__(self, persist_dir: Path | str = CHROMA_DIR) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            _COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, memory: Memory, embedding: list[float]) -> None:
        self._collection.upsert(
            ids=[memory.id], embeddings=[embedding], metadatas=[_metadata(memory)]
        )

    def query(
        self,
        embedding: list[float],
        n_results: int = 40,
        where: dict | None = None,
    ) -> list[tuple[str, float]]:
        """Return (memory_id, cosine_similarity) pairs, best first."""
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(n_results, max(self._collection.count(), 1)),
            where=where,
            include=["distances"],
        )
        ids, distances = result["ids"][0], result["distances"][0]
        return [(mid, 1.0 - dist) for mid, dist in zip(ids, distances)]

    def delete(self, memory_id: str) -> None:
        self._collection.delete(ids=[memory_id])

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        """Drop and recreate the collection (used by scripts/reset_db.py)."""
        self._client.delete_collection(_COLLECTION)
        self._collection = self._client.get_or_create_collection(
            _COLLECTION, metadata={"hnsw:space": "cosine"}
        )
