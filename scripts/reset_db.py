"""Rebuild the Chroma index from SQLite — the source of truth (§5).

SQLite is untouched; every active memory is re-embedded and re-upserted.
"""

from app.core.paths import ensure_data_dirs
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.sqlite.connection import create_connection
from app.memory.vector.chroma_client import ChromaVectorStore
from app.services.embedding_service import get_embedding_service

if __name__ == "__main__":
    ensure_data_dirs()
    repo = MemoryRepository(create_connection())
    store = ChromaVectorStore()
    store.reset()

    memories = repo.list(status=None)
    if memories:
        embeddings = get_embedding_service().embed_batch([m.content for m in memories])
        for memory, embedding in zip(memories, embeddings):
            store.upsert(memory, embedding)
    print(f"Rebuilt Chroma index: {store.count()} memories")
