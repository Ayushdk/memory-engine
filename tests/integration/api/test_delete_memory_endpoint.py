"""DELETE /api/v1/memories/{id} — the right to forget, across both stores."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_memory_admin, get_memory_repository
from app.engine.orchestrator.memory_admin import MemoryAdmin
from app.main import create_app
from app.memory.repositories.memory_repository import MemoryRepository
from tests.conftest import make_memory
from tests.integration.test_ingestion_pipeline import FakeEmbedder


@pytest.fixture
def repo(db_conn):
    return MemoryRepository(db_conn)


@pytest.fixture
def admin(repo, vector_store):
    return MemoryAdmin(repo, vector_store)


@pytest.fixture
def client(repo, admin):
    app = create_app()
    app.dependency_overrides[get_memory_repository] = lambda: repo
    app.dependency_overrides[get_memory_admin] = lambda: admin
    with TestClient(app) as client:
        yield client


@pytest.fixture
def seeded(repo, vector_store):
    memory = make_memory(content="forget me")
    repo.save(memory)
    vector_store.upsert(memory, FakeEmbedder().embed(memory.content))
    return memory


def test_delete_removes_from_both_stores(client, repo, vector_store, seeded):
    response = client.delete(f"/api/v1/memories/{seeded.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["synchronization_status"] == "in_sync"
    assert repo.get(seeded.id) is None
    assert vector_store.count() == 0


def test_unknown_id_is_404(client):
    response = client.delete("/api/v1/memories/mem_missing")
    assert response.status_code == 404
    assert "mem_missing" in response.json()["detail"]


def test_second_delete_is_404(client, seeded):
    assert client.delete(f"/api/v1/memories/{seeded.id}").status_code == 200
    assert client.delete(f"/api/v1/memories/{seeded.id}").status_code == 404


def test_sqlite_failure_leaves_chroma_untouched(client, repo, vector_store, seeded, monkeypatch):
    def boom(memory_id):
        raise RuntimeError("disk full")

    monkeypatch.setattr(repo, "delete", boom)
    body = client.delete(f"/api/v1/memories/{seeded.id}").json()

    assert body["success"] is False
    assert body["synchronization_status"] == "failed"
    assert "disk full" in body["reasoning"]
    assert vector_store.count() == 1  # index untouched
    monkeypatch.undo()
    assert repo.get(seeded.id) is not None  # truth store untouched


def test_chroma_failure_reports_sqlite_only(client, repo, vector_store, seeded, monkeypatch):
    def boom(memory_id):
        raise RuntimeError("index corrupted")

    monkeypatch.setattr(vector_store, "delete", boom)
    response = client.delete(f"/api/v1/memories/{seeded.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True  # memory IS gone from the source of truth
    assert body["synchronization_status"] == "sqlite_only"
    assert "reset_db" in body["reasoning"]
    assert repo.get(seeded.id) is None
