"""POST /api/v1/capture/{session_id}/reset — discard the unsynced capture.

Must remove exactly the not-yet-processed evidence (unsummarized raw
messages, open episode, working-memory buffer) and nothing that was already
generated from it (summarized rows, closed episodes, conversation summaries).
"""

from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import get_settings
from app.core import lifecycle
from app.main import create_app
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.sqlite.connection import create_connection
from app.memory.vector.chroma_client import ChromaVectorStore


def ingest(client, content, session_id="s1", role="user"):
    r = client.post(
        "/api/v1/ingest",
        json={"session_id": session_id, "platform": "chatgpt", "role": role, "content": content},
    )
    assert r.status_code == 200


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        return [1.0] + [0.0] * 383


def isolate_app(monkeypatch, tmp_path):
    fake_embedder = FakeEmbedder()
    get_settings.cache_clear()
    monkeypatch.setattr(lifecycle, "get_embedding_service", lambda: fake_embedder)
    monkeypatch.setattr(dependencies, "get_embedding_service", lambda: fake_embedder)
    monkeypatch.setattr(lifecycle, "create_connection", lambda: create_connection(tmp_path / "test.db"))
    monkeypatch.setattr(lifecycle, "ChromaVectorStore", lambda: ChromaVectorStore(tmp_path / "chroma"))


def test_reset_discards_unsummarized_capture_only(tmp_path, monkeypatch):
    isolate_app(monkeypatch, tmp_path)
    app = create_app()
    with TestClient(app) as client:
        ingest(client, "I prefer SQLite over Postgres for this.")
        ingest(client, "Noted — SQLite it is.", role="assistant")

        raw = app.state.raw_message_repository
        episodes = EpisodeRepository(app.state.db)
        assert len(raw.unsummarized("s1")) == 2
        assert episodes.get_open("s1") is not None

        # Pretend the first message was already folded into the rolling
        # summary — it must survive the reset.
        first = raw.list("s1")[0]
        raw.mark_summarized_by_ids([first.id])

        r = client.post("/api/v1/capture/s1/reset")
        assert r.status_code == 200
        body = r.json()
        assert body["raw_messages_discarded"] == 1
        assert body["episode_discarded"] is not None

        assert raw.unsummarized("s1") == []
        assert len(raw.list("s1")) == 1  # the summarized row survives
        assert episodes.get_open("s1") is None
        # Live working-memory buffer is empty: the next ingest starts fresh.
        assert app.state.ingestion_pipeline.working_memory.get_messages("s1") == []


def test_reset_of_an_idle_session_is_a_safe_no_op(tmp_path, monkeypatch):
    isolate_app(monkeypatch, tmp_path)
    with TestClient(create_app()) as client:
        r = client.post("/api/v1/capture/never-seen/reset")
        assert r.status_code == 200
        assert r.json() == {
            "session_id": "never-seen",
            "raw_messages_discarded": 0,
            "episode_discarded": None,
        }
