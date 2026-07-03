"""GET /api/v1/memories — browse with filters (architecture.md §6)."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_memory_repository
from app.main import create_app
from app.memory.repositories.memory_repository import MemoryRepository
from app.models.enums import MemoryCategory, MemoryStatus, MemoryView
from tests.conftest import make_memory

MEMORIES = "/api/v1/memories"


@pytest.fixture
def repo(db_conn):
    return MemoryRepository(db_conn)


@pytest.fixture
def client(repo):
    app = create_app()
    app.dependency_overrides[get_memory_repository] = lambda: repo
    with TestClient(app) as client:
        yield client


@pytest.fixture
def seeded(repo):
    memories = {
        "decision": make_memory(content="We use FastAPI."),
        "bug": make_memory(content="Ranking bug.", category=MemoryCategory.BUG),
        "profile": make_memory(
            content="Prefers diagrams.", category=MemoryCategory.PREFERENCE,
            view=MemoryView.PROFILE, project_id=None,
        ),
        "superseded": make_memory(content="We use Flask."),
    }
    for m in memories.values():
        repo.save(m)
    repo.set_status(memories["superseded"].id, MemoryStatus.SUPERSEDED)
    return memories


def ids(response):
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["memories"])
    return {m["id"] for m in body["memories"]}


def test_defaults_to_active_only(client, seeded):
    listed = ids(client.get(MEMORIES))
    assert listed == {seeded["decision"].id, seeded["bug"].id, seeded["profile"].id}


def test_filter_by_view(client, seeded):
    assert ids(client.get(MEMORIES, params={"view": "profile"})) == {seeded["profile"].id}


def test_filter_by_category(client, seeded):
    assert ids(client.get(MEMORIES, params={"category": "bug"})) == {seeded["bug"].id}


def test_filter_by_project(client, seeded):
    assert ids(client.get(MEMORIES, params={"project_id": "proj_openmemory"})) == {
        seeded["decision"].id,
        seeded["bug"].id,
    }


def test_filter_by_status(client, seeded):
    assert ids(client.get(MEMORIES, params={"status": "superseded"})) == {
        seeded["superseded"].id
    }


def test_combined_filters(client, seeded):
    listed = ids(
        client.get(MEMORIES, params={"project_id": "proj_openmemory", "category": "decision"})
    )
    assert listed == {seeded["decision"].id}


def test_limit(client, seeded):
    body = client.get(MEMORIES, params={"limit": 2}).json()
    assert body["count"] == 2


def test_empty_store(client):
    body = client.get(MEMORIES).json()
    assert body == {"memories": [], "count": 0}


def test_full_memory_shape(client, seeded):
    memory = next(
        m for m in client.get(MEMORIES).json()["memories"] if m["id"] == seeded["decision"].id
    )
    assert memory["content"] == "We use FastAPI."
    assert memory["category"] == "decision"
    assert memory["importance"] == 9
    assert memory["status"] == "active"
    assert memory["created_at"]


@pytest.mark.parametrize(
    "params",
    [{"view": "nonsense"}, {"category": "nope"}, {"status": "bogus"}, {"limit": 0}, {"limit": 9999}],
)
def test_invalid_params_are_422(client, params):
    assert client.get(MEMORIES, params=params).status_code == 422
