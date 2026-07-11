"""Context routes — transport only. Validate, resolve dependencies, delegate."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_context_pipeline, get_episode_tracker
from app.engine.episodes.tracker import EpisodeTracker
from app.engine.orchestrator.context_pipeline import ContextPipeline
from app.models.domain.context_pack import ContextPack
from app.models.schemas.context_requests import ContextRequest

router = APIRouter(tags=["context"])


@router.post("/context")
def context(
    request: ContextRequest,
    pipeline: Annotated[ContextPipeline, Depends(get_context_pipeline)],
    tracker: Annotated[EpisodeTracker, Depends(get_episode_tracker)],
) -> ContextPack:
    if request.mode == "sync":
        # Sync is an episode boundary: the user is carrying the work elsewhere.
        tracker.end_episode(request.session_id, "sync")
        return pipeline.build_sync_context(request.session_id, request.project_id)
    return pipeline.build_context(request.session_id, request.query, request.project_id)
