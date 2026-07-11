"""Episode routes — transport only. Read-side for verification, dogfooding,
and the Dashboard's Timeline/Workspace views."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_episode_repository
from app.memory.repositories.episode_repository import EpisodeRepository
from app.models.domain.episode import Episode

router = APIRouter(tags=["episodes"])


@router.get("/episodes")
def list_episodes(
    repository: Annotated[EpisodeRepository, Depends(get_episode_repository)],
    session_id: str | None = None,
    project_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Episode]:
    return repository.list(session_id=session_id, project_id=project_id, limit=limit)
