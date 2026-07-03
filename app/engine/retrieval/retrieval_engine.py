"""Candidate Retrieval Engine (architecture.md §4): "which memories COULD be
relevant?" — Chroma similarity search under hard filters (status=active,
optional project), then hydration from SQLite. Candidate selection only; the
Ranking Engine (ranking_engine.py) decides which candidates are best.
"""

from dataclasses import dataclass, field

from app.core.config import get_settings
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.vector.chroma_client import ChromaVectorStore, active_where
from app.models.domain.memory import Memory
from app.services.embedding_service import EmbeddingService


@dataclass(frozen=True)
class RetrievalResult:
    query_embedding: list[float]
    candidate_memory_ids: list[str]
    retrieved_memories: list[Memory]
    # cosine similarity per candidate id — the ranking engine's first input
    retrieval_metadata: dict = field(default_factory=dict)


class RetrievalEngine:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: ChromaVectorStore,
        repository: MemoryRepository,
    ) -> None:
        self._embeddings = embedding_service
        self._vector_store = vector_store
        self._repository = repository

    def retrieve(
        self,
        query: str,
        project_id: str | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        top_k = top_k or get_settings().retrieval_candidates
        query_embedding = self._embeddings.embed(query)

        hits = self._vector_store.query(
            query_embedding, n_results=top_k, where=active_where(project_id)
        )
        similarities = dict(hits)

        # Hydrate from the source of truth; ids missing in SQLite mean a stale
        # index (repairable via reset_db.py) and are dropped, not invented.
        memories = [m for mid, _ in hits if (m := self._repository.get(mid))]

        return RetrievalResult(
            query_embedding=query_embedding,
            candidate_memory_ids=[m.id for m in memories],
            retrieved_memories=memories,
            retrieval_metadata={"similarities": similarities, "requested_top_k": top_k},
        )
