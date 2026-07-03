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
        retrieval = self._retrieval.retrieve(query, project_id)
        ranking = self._ranking.rank(retrieval, project_id)

        # Profile facts are mandatory pack content (§7) and would be excluded
        # by the project hard filter, so they come from the source of truth.
        profile_memories = self._repository.list(view=MemoryView.PROFILE)

        pack = self._builder.build(
            ranking,
            session_id,
            project_state=None,  # populated by Phase 5 consolidation
            profile_memories=profile_memories,
        )

        if ranking.selected_memory_ids:
            self._repository.record_access(ranking.selected_memory_ids)

        return pack
