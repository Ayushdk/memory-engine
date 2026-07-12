"""Workspace routes — transport only. State + archive/reset controls for the
extension popup and the Dashboard's Workspace view."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_workspace_repository
from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.models.domain.workspace import Workspace, WorkspaceArchive

router = APIRouter(tags=["workspace"])


@router.get("/workspace/{project_id}")
def get_workspace(
    project_id: str,
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> Workspace:
    return repository.get(project_id)


@router.post("/workspace/{project_id}/reset")
def reset_workspace(
    project_id: str,
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> dict:
    repository.reset(project_id)
    return {"ok": True}


@router.post("/workspace/{project_id}/archive")
def archive_workspace(
    project_id: str,
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> dict:
    archive_id = repository.archive(project_id)
    return {"ok": True, "archive_id": archive_id}


@router.get("/workspace/{project_id}/archives")
def list_archives(
    project_id: str,
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> list[WorkspaceArchive]:
    return repository.list_archives(project_id)
