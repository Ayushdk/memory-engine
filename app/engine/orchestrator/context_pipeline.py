"""Context Pipeline (architecture.md §2): retrieve → rank → build → ContextPack.

Coordination only, like the ingestion pipeline. Access bookkeeping happens
here — only after ranking has picked the final selection, so candidate
memories that lost the re-rank never get their stats inflated.
"""

from datetime import timedelta

from app.core.config import get_settings
from app.engine.context.context_builder import ContextBuilder
from app.engine.retrieval.ranking_engine import RankingEngine
from app.engine.retrieval.retrieval_engine import RetrievalEngine, RetrievalResult
from app.memory.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.project_state_repository import ProjectStateRepository
from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.models.domain.context_pack import ContextPack
from app.models.enums import MemoryView
from app.utils.time import utc_now


class ContextPipeline:
    def __init__(
        self,
        retrieval_engine: RetrievalEngine,
        ranking_engine: RankingEngine,
        context_builder: ContextBuilder,
        repository: MemoryRepository,
        workspace_repository: WorkspaceRepository | None = None,
        project_state_repository: ProjectStateRepository | None = None,
        conversation_summary_repository: ConversationSummaryRepository | None = None,
    ) -> None:
        self._retrieval = retrieval_engine
        self._ranking = ranking_engine
        self._builder = context_builder
        self._repository = repository
        self._workspaces = workspace_repository
        self._project_states = project_state_repository
        self._conversation_summaries = conversation_summary_repository

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
        include_brain: bool = False,
    ) -> ContextPack:
        """State-driven: 'what should a brand-new conversation receive first?'
        This is a conversation-compression sync, not a retrieval feature: by
        default it carries only the latest working summary, project context,
        and task state. Long-term/personal-brain memories are brain content —
        opt in with `include_brain=True` when explicitly requested."""
        if include_brain:
            # No query → no similarity signal; ranking runs on importance +
            # recency (+ access), surfacing decisions/architecture/goals via
            # the scorer's category base scores.
            retrieval = self._retrieval.retrieve_for_sync(project_id)
        else:
            retrieval = RetrievalResult(query_embedding=[], candidate_memory_ids=[], retrieved_memories=[])
        # The workspace transfer summary is the "where the work stands"
        # briefing — the continuity core of a sync pack.
        workspace = None
        if project_id and self._workspaces:
            workspace = self._workspaces.get(project_id).transfer_summary or None
        # Sync means "continue whatever I worked on last" — not "continue
        # this session". So the rolling Current Context Summary is always
        # the most recently updated one across ALL sessions/platforms,
        # never scoped to the requesting session_id.
        conversation_summary = None
        if self._conversation_summaries:
            since = utc_now() - timedelta(minutes=get_settings().recap_freshness_minutes)
            latest = self._conversation_summaries.latest(since=since)
            conversation_summary = latest.summary if latest else None
        return self._assemble(
            session_id, retrieval, project_id, workspace=workspace,
            conversation_summary=conversation_summary, include_brain=include_brain,
        )

    def _assemble(
        self, session_id, retrieval, project_id, workspace=None,
        conversation_summary=None, include_brain: bool = True,
    ) -> ContextPack:
        ranking = self._ranking.rank(retrieval, project_id)

        # Profile facts are mandatory pack content (§7) for query mode; sync
        # mode default-excludes them (brain content, opt-in only).
        profile_memories = self._repository.list(view=MemoryView.PROFILE) if include_brain else []

        project_state = None
        if project_id and self._project_states:
            state = self._project_states.latest(project_id)
            project_state = state.content if state else None

        pack = self._builder.build(
            ranking,
            session_id,
            project_state=project_state,
            workspace=workspace,
            conversation_summary=conversation_summary,
            profile_memories=profile_memories,
        )

        if ranking.selected_memory_ids:
            self._repository.record_access(ranking.selected_memory_ids)

        return pack
