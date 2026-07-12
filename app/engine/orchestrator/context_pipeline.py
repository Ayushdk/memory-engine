"""Context Pipeline (architecture.md §2): retrieve → rank → build → ContextPack.

Coordination only, like the ingestion pipeline. Access bookkeeping happens
here — only after ranking has picked the final selection, so candidate
memories that lost the re-rank never get their stats inflated.
"""

from datetime import timedelta

from app.core.config import get_settings
from app.engine.context.context_builder import ContextBuilder
from app.engine.context.session_recap import SessionRecapBuilder
from app.engine.retrieval.ranking_engine import RankingEngine
from app.engine.retrieval.retrieval_engine import RetrievalEngine
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.session_repository import SessionRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.models.domain.context_pack import ContextPack, RecentConversation
from app.models.enums import MemoryView
from app.utils.time import utc_now


class ContextPipeline:
    def __init__(
        self,
        retrieval_engine: RetrievalEngine,
        ranking_engine: RankingEngine,
        context_builder: ContextBuilder,
        repository: MemoryRepository,
        session_repository: SessionRepository | None = None,
        working_memory_repository: WorkingMemoryRepository | None = None,
        recap_builder: SessionRecapBuilder | None = None,
        workspace_repository: WorkspaceRepository | None = None,
    ) -> None:
        self._retrieval = retrieval_engine
        self._ranking = ranking_engine
        self._builder = context_builder
        self._repository = repository
        self._sessions = session_repository
        self._snapshots = working_memory_repository
        self._recap_builder = recap_builder or SessionRecapBuilder()
        self._workspaces = workspace_repository

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
        recap = self._build_recap(requesting_session_id=session_id)
        # The workspace transfer summary is the "where the work stands"
        # briefing — the continuity core of a sync pack.
        workspace = None
        if project_id and self._workspaces:
            workspace = self._workspaces.get(project_id).transfer_summary or None
        return self._assemble(
            session_id, retrieval, project_id, recent_conversation=recap, workspace=workspace
        )

    def _build_recap(self, requesting_session_id: str) -> RecentConversation | None:
        """Handoff excerpt from the single most recently active OTHER session
        within the freshness window (the buffer the user just left behind)."""
        if self._sessions is None or self._snapshots is None:
            return None
        since = utc_now() - timedelta(minutes=get_settings().recap_freshness_minutes)
        source = next(
            (s for s in self._sessions.list_active(since) if s.id != requesting_session_id),
            None,
        )
        if source is None:
            return None
        return self._recap_builder.build(source, self._snapshots.load(source.id))

    def _assemble(
        self, session_id, retrieval, project_id, recent_conversation=None, workspace=None
    ) -> ContextPack:
        ranking = self._ranking.rank(retrieval, project_id)

        # Profile facts are mandatory pack content (§7) and would be excluded
        # by the project hard filter, so they come from the source of truth.
        profile_memories = self._repository.list(view=MemoryView.PROFILE)

        pack = self._builder.build(
            ranking,
            session_id,
            project_state=None,  # populated by reflection (Phase 4)
            workspace=workspace,
            profile_memories=profile_memories,
            recent_conversation=recent_conversation,
        )

        if ranking.selected_memory_ids:
            self._repository.record_access(ranking.selected_memory_ids)

        return pack
