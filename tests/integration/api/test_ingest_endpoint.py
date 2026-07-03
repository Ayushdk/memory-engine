"""POST /api/v1/ingest — transport-layer tests. The pipeline dependency is
overridden with one backed by tmp SQLite/Chroma and the deterministic fake
embedder, so these tests exercise validation + wiring, not MiniLM."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_ingestion_pipeline
from app.main import create_app
from tests.integration.test_ingestion_pipeline import FASTAPI_MSG, FLASK_MSG, pipeline  # noqa: F401

INGEST = "/api/v1/ingest"


@pytest.fixture
def client(pipeline):  # noqa: F811
    app = create_app()
    app.dependency_overrides[get_ingestion_pipeline] = lambda: pipeline
    with TestClient(app) as client:
        yield client


def payload(content, **overrides):
    return {
        "session_id": "s1",
        "platform": "chatgpt",
        "role": "user",
        "content": content,
        "project_id": "proj_x",
        **overrides,
    }


def test_store(client):
    response = client.post(INGEST, json=payload(FLASK_MSG))
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "store"
    assert body["success"] is True
    assert body["synchronization_status"] == "in_sync"
    assert body["memory_id"].startswith("mem_")
    assert body["classification"]["category"] == "decision"
    assert body["routing"]["view"] == "project"


def test_update_supersedes(client):
    old = client.post(INGEST, json=payload(FLASK_MSG)).json()
    new = client.post(INGEST, json=payload(FASTAPI_MSG)).json()
    assert new["action"] == "update"
    assert new["reasoning"] == f"supersedes {old['memory_id']}"


def test_ignore(client):
    body = client.post(INGEST, json=payload("Thanks!")).json()
    assert body["action"] == "ignore"
    assert body["synchronization_status"] == "skipped"
    assert body["memory_id"] is None
    assert body["scoring"] is None


@pytest.mark.parametrize(
    "bad",
    [
        {},  # everything missing
        payload(""),  # empty content
        payload("hi", role="system"),  # role outside the enum
        {"session_id": "s1", "platform": "chatgpt", "role": "user"},  # no content
    ],
)
def test_invalid_requests_are_422(client, bad):
    assert client.post(INGEST, json=bad).status_code == 422


def test_sqlite_failure_is_structured_not_a_crash(client, pipeline, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        pipeline._repository, "save", lambda m: (_ for _ in ()).throw(RuntimeError("disk full"))
    )
    response = client.post(INGEST, json=payload(FLASK_MSG))
    assert response.status_code == 200  # structured pipeline failure, not a 500
    body = response.json()
    assert body["success"] is False
    assert body["synchronization_status"] == "failed"


def test_chroma_failure_reports_sqlite_only(client, pipeline, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        pipeline._vector_store,
        "upsert",
        lambda m, e: (_ for _ in ()).throw(RuntimeError("index corrupted")),
    )
    body = client.post(INGEST, json=payload(FLASK_MSG)).json()
    assert body["success"] is True
    assert body["synchronization_status"] == "sqlite_only"
