"""Context Pipeline (architecture.md §2): retrieve → rank → build → ContextPack.

Coordination only, like the ingestion pipeline. Access bookkeeping happens
here — only after ranking has picked the final selection, so candidate
memories that lost the re-rank never get their stats inflated.
"""

from app.engine.context.context_builder import ContextBuilder
from app.engine.retrieval.ranking_engine import RankingEngine
from app.engine.retrieval.retrieval_engine import RetrievalEngine
from app.memory.repositories.memory_repository import MemoryRepository
from app.models.domain.context_pack import ContextPack
from app.models.enums import MemoryView


class ContextPipeline:
    def __init__(
        self,
        retrieval_engine: RetrievalEngine,
        ranking_engine: RankingEngine,
        context_builder: ContextBuilder,
        repository: MemoryRepository,
    ) -> None:
        self._retrieval = retrieval_engine
        self._ranking = ranking_engine
        self._builder = context_builder
        self._repository = repository

    def build_context(
        self,
        session_id: str,
        query: str,
        project_id: str | None = None,
    ) -> ContextPack:
        """Query-driven: mid-conversation retrieval, similarity-weighted."""
        retrieval = self._retrieval.retrieve(query, project_id)
        return self._assemble(session_id, retrieval, project_id)

    def build_sync_context(
        self,
        session_id: str,
        project_id: str | None = None,
    ) -> ContextPack:
        """State-driven: 'what should a brand-new conversation receive first?'
        No query → no similarity signal; ranking runs on importance + recency
        (+ access), which naturally surfaces decisions/architecture/goals via
        the scorer's category base scores."""
        retrieval = self._retrieval.retrieve_for_sync(project_id)
        return self._assemble(session_id, retrieval, project_id)

    def _assemble(self, session_id, retrieval, project_id) -> ContextPack:
        ranking = self._ranking.rank(retrieval, project_id)

        # Profile facts are mandatory pack content (§7) and would be excluded
        # by the project hard filter, so they come from the source of truth.
        profile_memories = self._repository.list(view=MemoryView.PROFILE)

        pack = self._builder.build(
            ranking,
            session_id,
            project_state=None,  # populated by consolidation (M4+)
            profile_memories=profile_memories,
        )

        if ranking.selected_memory_ids:
            self._repository.record_access(ranking.selected_memory_ids)

        return pack
