"""Token auth + CORS posture."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_memory_repository
from app.core.config import get_settings
from app.main import create_app
from app.memory.repositories.memory_repository import MemoryRepository

MEMORIES = "/api/v1/memories"
EXTENSION_ORIGIN = "chrome-extension://abcdefghijklmnop"


@pytest.fixture
def secured_client(db_conn, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "api_token", "s3cret", raising=True)
    monkeypatch.setattr(settings, "cors_origins", [EXTENSION_ORIGIN], raising=True)
    app = create_app()  # after patching: CORS config is read at creation time
    app.dependency_overrides[get_memory_repository] = lambda: MemoryRepository(db_conn)
    with TestClient(app) as client:
        yield client


def test_missing_token_is_401(secured_client):
    assert secured_client.get(MEMORIES).status_code == 401


def test_wrong_token_is_401(secured_client):
    r = secured_client.get(MEMORIES, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_wrong_scheme_is_401(secured_client):
    r = secured_client.get(MEMORIES, headers={"Authorization": "Basic s3cret"})
    assert r.status_code == 401


def test_correct_token_passes(secured_client):
    r = secured_client.get(MEMORIES, headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200


def test_health_stays_open_without_token(secured_client):
    assert secured_client.get("/api/v1/health").status_code == 200


def test_auth_disabled_when_token_unset(db_conn):
    # default settings: api_token is None → guard is a no-op (bare local dev)
    app = create_app()
    app.dependency_overrides[get_memory_repository] = lambda: MemoryRepository(db_conn)
    with TestClient(app) as client:
        assert client.get(MEMORIES).status_code == 200


def test_cors_allows_extension_origin(secured_client):
    r = secured_client.options(
        MEMORIES,
        headers={
            "Origin": EXTENSION_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == EXTENSION_ORIGIN


def test_cors_denies_unknown_origin(secured_client):
    r = secured_client.options(
        MEMORIES,
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers


def test_no_cors_middleware_by_default(db_conn):
    # cors_origins empty (default) → no ACAO header ever emitted
    app = create_app()
    app.dependency_overrides[get_memory_repository] = lambda: MemoryRepository(db_conn)
    with TestClient(app) as client:
        r = client.get(MEMORIES, headers={"Origin": EXTENSION_ORIGIN})
        assert "access-control-allow-origin" not in r.headers
