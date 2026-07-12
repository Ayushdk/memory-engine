"""Project routes — transport only. Read-side for the Dashboard's project
switcher: which projects has the engine actually seen work for."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_project_repository
from app.memory.repositories.project_repository import ProjectRepository
from app.models.domain.project import Project

router = APIRouter(tags=["projects"])


@router.get("/projects")
def list_projects(
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> list[Project]:
    return repository.list()
