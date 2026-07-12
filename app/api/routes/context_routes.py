"""Context routes — transport only. Validate, resolve dependencies, delegate."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_context_pipeline,
    get_conversation_summary_repository,
    get_episode_repository,
    get_episode_tracker,
    get_project_repository,
    get_raw_message_repository,
    get_working_memory_repository,
    get_workspace_repository,
)
from app.engine.episodes.tracker import EpisodeTracker
from app.engine.llm.provider import create_provider
from app.engine.orchestrator.context_pipeline import ContextPipeline
from app.jobs.episode_jobs import summarize_and_update_workspace
from app.memory.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.project_repository import ProjectRepository
from app.memory.repositories.raw_message_repository import RawMessageRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.models.domain.context_pack import ContextPack
from app.models.schemas.context_requests import ContextRequest

router = APIRouter(tags=["context"])


@router.post("/context")
async def context(
    request: ContextRequest,
    pipeline: Annotated[ContextPipeline, Depends(get_context_pipeline)],
    tracker: Annotated[EpisodeTracker, Depends(get_episode_tracker)],
    episodes: Annotated[EpisodeRepository, Depends(get_episode_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    working_memory: Annotated[WorkingMemoryRepository, Depends(get_working_memory_repository)],
    raw_messages: Annotated[RawMessageRepository, Depends(get_raw_message_repository)],
    conversation_summaries: Annotated[
        ConversationSummaryRepository, Depends(get_conversation_summary_repository)
    ],
) -> ContextPack:
    if request.mode == "sync":
        # Sync is an episode boundary: the user is carrying the work
        # elsewhere. Await the summarize+workspace fast phase inline so the
        # pack we build below always reflects this episode, never a stale
        # workspace — the background job (enqueued by the tracker's on_close)
        # redoes the same call, which is a no-op by the time it runs.
        episode = tracker.end_episode(request.session_id, "sync")
        if episode is not None:
            await summarize_and_update_workspace(
                episode.id, episodes, working_memory, workspaces, create_provider("summarizer"),
                projects=projects, raw_messages=raw_messages,
                conversation_summaries=conversation_summaries,
            )
        return pipeline.build_sync_context(
            request.session_id, request.project_id, include_brain=request.include_brain
        )
    return pipeline.build_context(request.session_id, request.query, request.project_id)
