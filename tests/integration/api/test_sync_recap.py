"""Sync mode's Recent Session Recap, end-to-end: ingest on 'chatgpt', sync
from a brand-new 'claude' session, inherit the momentum."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_context_pipeline, get_ingestion_pipeline
from app.engine.context.context_builder import ContextBuilder
from app.engine.orchestrator.context_pipeline import ContextPipeline
from app.engine.retrieval.ranking_engine import RankingEngine
from app.engine.retrieval.retrieval_engine import RetrievalEngine
from app.main import create_app
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.session_repository import SessionRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from tests.integration.test_ingestion_pipeline import FakeEmbedder, pipeline  # noqa: F401

CONTEXT = "/api/v1/context"
INGEST = "/api/v1/ingest"


@pytest.fixture
def client(pipeline, db_conn, vector_store):  # noqa: F811
    repo = MemoryRepository(db_conn)
    context_pipeline = ContextPipeline(
        retrieval_engine=RetrievalEngine(FakeEmbedder(), vector_store, repo),
        ranking_engine=RankingEngine(),
        context_builder=ContextBuilder(),
        repository=repo,
        session_repository=SessionRepository(db_conn),
        working_memory_repository=WorkingMemoryRepository(db_conn),
    )
    app = create_app()
    app.dependency_overrides[get_ingestion_pipeline] = lambda: pipeline
    app.dependency_overrides[get_context_pipeline] = lambda: context_pipeline
    with TestClient(app) as client:
        yield client


def ingest(client, content, session_id="chatgpt-s1", role="user"):
    r = client.post(
        INGEST,
        json={
            "session_id": session_id,
            "platform": "chatgpt",
            "role": role,
            "content": content,
            "project_id": "proj_x",
        },
    )
    assert r.status_code == 200
    return r.json()


def sync(client, session_id="claude-s1", include_brain=True):
    r = client.post(
        CONTEXT,
        json={"session_id": session_id, "mode": "sync", "include_brain": include_brain},
    )
    assert r.status_code == 200
    return r.json()


def test_sync_from_new_session_inherits_recap(client):
    ingest(client, "We decided to use SQLite as the source of truth.")  # stored
    ingest(client, "The tricky part is the retrieval endpoint design.")  # unstored nuance
    ingest(client, "Right, and the ranking needs a recency signal.", role="assistant")

    pack = sync(client)
    recap = pack["sections"]["recent_conversation"]
    assert recap["platform"] == "chatgpt"
    assert recap["minutes_ago"] == 0
    assert recap["messages"] == [
        "User: The tricky part is the retrieval endpoint design.",
        "Assistant: Right, and the ranking needs a recency signal.",
    ]
    # the stored decision is NOT repeated in the recap — it's a relevant memory
    assert [m["summary"] for m in pack["sections"]["relevant_memories"]] == [
        "We decided to use SQLite as the source of truth."
    ]


def test_own_session_gets_no_recap(client):
    ingest(client, "Some ongoing discussion detail.")
    pack = sync(client, session_id="chatgpt-s1")  # syncing the session we're already in
    assert pack["sections"]["recent_conversation"] is None


def test_no_recent_session_means_no_recap(client, monkeypatch):
    from app.core.config import get_settings

    ingest(client, "Some ongoing discussion detail.")
    monkeypatch.setattr(get_settings(), "recap_freshness_minutes", -1, raising=True)
    assert sync(client)["sections"]["recent_conversation"] is None


def test_smalltalk_never_reaches_the_recap(client):
    ingest(client, "Deep design discussion happening here.")
    ingest(client, "Thanks!")
    assert sync(client)["sections"]["recent_conversation"]["messages"] == [
        "User: Deep design discussion happening here."
    ]


def test_query_mode_has_no_recap(client):
    ingest(client, "Some ongoing discussion detail.")
    r = client.post(CONTEXT, json={"session_id": "claude-s1", "query": "anything"})
    assert r.json()["sections"]["recent_conversation"] is None


def test_recap_comes_from_most_recent_session(client):
    ingest(client, "Older conversation detail.", session_id="chatgpt-old")
    ingest(client, "Newest conversation detail.", session_id="chatgpt-new")

    recap = sync(client)["sections"]["recent_conversation"]
    assert recap["messages"] == ["User: Newest conversation detail."]
