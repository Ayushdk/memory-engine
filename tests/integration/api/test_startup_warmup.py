"""Engine startup warms the embedding model without blocking /health."""

import time

from fastapi.testclient import TestClient

import app.core.lifecycle as lifecycle
from app.main import create_app


def test_warmup_runs_in_background(monkeypatch):
    calls = []

    class StubService:
        def embed(self, text):
            calls.append(text)
            return [0.0]

    monkeypatch.setattr(lifecycle, "get_embedding_service", lambda: StubService())

    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health").status_code == 200  # not blocked
        deadline = time.time() + 5
        while not calls and time.time() < deadline:
            time.sleep(0.05)
    assert calls == ["warmup"]


def test_warmup_failure_does_not_kill_startup(monkeypatch):
    class BrokenService:
        def embed(self, text):
            raise RuntimeError("no model")

    monkeypatch.setattr(lifecycle, "get_embedding_service", lambda: BrokenService())

    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health").status_code == 200
