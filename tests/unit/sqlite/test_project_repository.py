"""ProjectRepository: projects become known via get_or_create, not declared up front."""

from app.memory.repositories.project_repository import ProjectRepository
from app.models.enums import ProjectStatus


def test_get_or_create_creates_once(db_conn):
    repo = ProjectRepository(db_conn)

    first = repo.get_or_create("proj_openmemory")
    second = repo.get_or_create("proj_openmemory")

    assert first.id == second.id == "proj_openmemory"
    assert first.status is ProjectStatus.ACTIVE
    assert repo.list() == [first]


def test_get_or_create_does_not_overwrite_existing_state(db_conn):
    repo = ProjectRepository(db_conn)
    project = repo.get_or_create("proj_openmemory")
    project = project.model_copy(update={"name": "OpenMemory"})
    repo.save(project)

    again = repo.get_or_create("proj_openmemory")

    assert again.name == "OpenMemory"
