"""Context routes — transport only. Validate, resolve dependencies, delegate."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from loguru import logger

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
        #
        # This inline path can chain up to three sequential local-LLM calls
        # (episode summary, workspace update, conversation summary) before a
        # response goes out — slow enough on local Ollama to blow past a
        # client's request timeout even though the backend finishes fine.
        # Stage timing is logged so a slow step is visible without guessing.
        t0 = time.monotonic()
        logger.info("sync: request received session={}", request.session_id)
        try:
            episode = tracker.end_episode(request.session_id, "sync")
            logger.info(
                "sync: end_episode done episode={} elapsed={:.2f}s",
                episode.id if episode else None, time.monotonic() - t0,
            )

            if episode is not None:
                t1 = time.monotonic()
                await summarize_and_update_workspace(
                    episode.id, episodes, working_memory, workspaces,
                    create_provider("summarizer"),
                    projects=projects, raw_messages=raw_messages,
                    conversation_summaries=conversation_summaries,
                )
                logger.info(
                    "sync: summarize_and_update_workspace done elapsed={:.2f}s "
                    "total_elapsed={:.2f}s",
                    time.monotonic() - t1, time.monotonic() - t0,
                )

            t2 = time.monotonic()
            pack = pipeline.build_sync_context(
                request.session_id, request.project_id, include_brain=request.include_brain
            )
            logger.info(
                "sync: build_sync_context done elapsed={:.2f}s total_elapsed={:.2f}s",
                time.monotonic() - t2, time.monotonic() - t0,
            )
        except Exception:
            logger.exception(
                "sync: failed after {:.2f}s session={}",
                time.monotonic() - t0, request.session_id,
            )
            raise

        # FastAPI serializes `pack` (response_model=ContextPack) and returns
        # HTTP 200 after this point — logged here so "did the backend ever
        # actually respond" is answered by the log, not inferred.
        logger.info(
            "sync: returning HTTP 200 session={} total_elapsed={:.2f}s",
            request.session_id, time.monotonic() - t0,
        )
        return pack
    return pipeline.build_context(request.session_id, request.query, request.project_id)
