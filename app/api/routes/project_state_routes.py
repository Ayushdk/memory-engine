"""Project State routes — transport only. Read-side for dogfooding and the
Dashboard's future Timeline/Overview views."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_project_state_repository
from app.memory.repositories.project_state_repository import ProjectStateRepository
from app.models.domain.project_state import ProjectState

router = APIRouter(tags=["project-state"])


@router.get("/projects/{project_id}/state")
def get_project_state(
    project_id: str,
    repository: Annotated[ProjectStateRepository, Depends(get_project_state_repository)],
) -> ProjectState:
    state = repository.latest(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="no project state yet")
    return state


@router.get("/projects/{project_id}/state/versions")
def list_project_state_versions(
    project_id: str,
    repository: Annotated[ProjectStateRepository, Depends(get_project_state_repository)],
) -> list[ProjectState]:
    return repository.list_versions(project_id)
