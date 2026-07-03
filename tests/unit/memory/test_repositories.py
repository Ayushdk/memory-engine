from tests.conftest import make_memory

from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.project_repository import ProjectRepository
from app.models.domain.memory import Source
from app.models.domain.project import Project
from app.models.enums import MemoryStatus, MemoryView


def test_memory_round_trip(db_conn):
    repo = MemoryRepository(db_conn)
    memory = make_memory(source=Source(platform="chatgpt", session_id="s1", role="user"))
    repo.save(memory)
    assert repo.get(memory.id) == memory


def test_get_missing_returns_none(db_conn):
    assert MemoryRepository(db_conn).get("mem_missing") is None


def test_list_filters(db_conn):
    repo = MemoryRepository(db_conn)
    project_mem = make_memory()
    profile_mem = make_memory(view=MemoryView.PROFILE, project_id=None, content="Prefers diagrams")
    repo.save(project_mem)
    repo.save(profile_mem)

    assert [m.id for m in repo.list(view=MemoryView.PROJECT)] == [project_mem.id]
    assert [m.id for m in repo.list(project_id="proj_openmemory")] == [project_mem.id]
    assert len(repo.list()) == 2


def test_set_status_excludes_from_active_list(db_conn):
    repo = MemoryRepository(db_conn)
    memory = make_memory()
    repo.save(memory)
    repo.set_status(memory.id, MemoryStatus.SUPERSEDED)

    assert repo.list() == []  # default filter is status=active
    assert repo.get(memory.id).status is MemoryStatus.SUPERSEDED


def test_record_access(db_conn):
    repo = MemoryRepository(db_conn)
    memory = make_memory()
    repo.save(memory)
    repo.record_access([memory.id])

    fetched = repo.get(memory.id)
    assert fetched.access_count == 1
    assert fetched.last_accessed_at is not None


def test_delete(db_conn):
    repo = MemoryRepository(db_conn)
    memory = make_memory()
    repo.save(memory)
    assert repo.delete(memory.id) is True
    assert repo.get(memory.id) is None
    assert repo.delete(memory.id) is False


def test_project_round_trip(db_conn):
    repo = ProjectRepository(db_conn)
    project = Project(name="OpenMemory", state={"decisions": ["FastAPI"]})
    repo.save(project)
    assert repo.get(project.id) == project
    assert repo.list() == [project]
