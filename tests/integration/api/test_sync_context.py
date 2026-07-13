"""POST /api/v1/context mode=sync — the query-less Sync Context pack.

Sync reads only SQLite (no embeddings, no Chroma), so memories are seeded
directly through the repository with controlled importance/recency.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_context_pipeline
from app.engine.context.context_builder import ContextBuilder
from app.engine.orchestrator.context_pipeline import ContextPipeline
from app.engine.retrieval.ranking_engine import RankingEngine
from app.engine.retrieval.retrieval_engine import RetrievalEngine
from app.main import create_app
from app.memory.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.project_state_repository import ProjectStateRepository
from app.models.enums import MemoryCategory, MemoryView
from app.utils.time import utc_now
from tests.conftest import make_memory
from tests.integration.test_ingestion_pipeline import FakeEmbedder

CONTEXT = "/api/v1/context"


@pytest.fixture
def repo(db_conn):
    return MemoryRepository(db_conn)


@pytest.fixture
def client(repo, vector_store):
    pipeline = ContextPipeline(
        retrieval_engine=RetrievalEngine(FakeEmbedder(), vector_store, repo),
        ranking_engine=RankingEngine(),
        context_builder=ContextBuilder(),
        repository=repo,
    )
    app = create_app()
    app.dependency_overrides[get_context_pipeline] = lambda: pipeline
    with TestClient(app) as client:
        yield client


def seed(repo, content, category=MemoryCategory.DECISION, importance=9, **overrides):
    memory = make_memory(
        content=content, summary=None, category=category, importance=importance, **overrides
    )
    repo.save(memory)
    return memory


def sync(client, project_id=None, include_brain=False, session_id="s1"):
    r = client.post(
        CONTEXT,
        json={
            "session_id": session_id, "mode": "sync", "project_id": project_id,
            "include_brain": include_brain,
        },
    )
    assert r.status_code == 200
    return r.json()


def test_sync_default_excludes_brain_content(client, repo):
    # Injection rules: by default a sync pack carries only the working
    # summary/project context/task state — long-term memories are opt-in.
    seed(
        repo, "Prefers diagrams.", MemoryCategory.PREFERENCE,
        importance=7, view=MemoryView.PROFILE, project_id=None,
    )
    seed(repo, "Which cache should we pick?", MemoryCategory.QUESTION, importance=3)
    seed(repo, "We use FastAPI.", importance=10)

    sections = sync(client)["sections"]
    assert sections["profile"] == []
    assert sections["open_questions"] == []
    assert sections["relevant_memories"] == []


def test_sync_pack_prioritizes_importance(client, repo):
    seed(repo, "Minor task cleanup.", MemoryCategory.TASK, importance=4)
    seed(repo, "We use FastAPI.", MemoryCategory.DECISION, importance=10)
    seed(repo, "Engine-first architecture.", MemoryCategory.ARCHITECTURE, importance=9)
    seed(repo, "Ship V1 by March.", MemoryCategory.GOAL, importance=8)

    summaries = [
        m["summary"] for m in sync(client, include_brain=True)["sections"]["relevant_memories"]
    ]
    assert summaries == [
        "We use FastAPI.",
        "Engine-first architecture.",
        "Ship V1 by March.",
        "Minor task cleanup.",
    ]


def test_recency_breaks_importance_ties(client, repo):
    old_time = utc_now() - timedelta(days=90)
    seed(repo, "Old decision.", importance=9, created_at=old_time, updated_at=old_time)
    seed(repo, "Fresh decision.", importance=9)

    summaries = [
        m["summary"] for m in sync(client, include_brain=True)["sections"]["relevant_memories"]
    ]
    assert summaries == ["Fresh decision.", "Old decision."]


def test_project_filtering(client, repo):
    seed(repo, "Ours.", project_id="proj_x")
    seed(repo, "Theirs.", project_id="proj_y")

    summaries = [
        m["summary"]
        for m in sync(client, project_id="proj_x", include_brain=True)["sections"]["relevant_memories"]
    ]
    assert summaries == ["Ours."]


def test_profile_and_open_questions_included_when_requested(client, repo):
    seed(
        repo, "Prefers diagrams.", MemoryCategory.PREFERENCE,
        importance=7, view=MemoryView.PROFILE, project_id=None,
    )
    seed(repo, "Which cache should we pick?", MemoryCategory.QUESTION, importance=3)
    seed(repo, "We use FastAPI.")

    sections = sync(client, include_brain=True)["sections"]
    assert sections["profile"] == ["Prefers diagrams."]
    assert sections["open_questions"] == ["Which cache should we pick?"]
    assert [m["summary"] for m in sections["relevant_memories"]] == ["We use FastAPI."]


def test_empty_project(client, repo):
    seed(repo, "Other project fact.", project_id="proj_y")
    pack = sync(client, project_id="proj_empty", include_brain=True)
    assert pack["sections"]["relevant_memories"] == []
    assert pack["sections"]["open_questions"] == []


def test_deterministic_output(client, repo):
    for i in range(4):
        seed(repo, f"Decision {i}.", importance=9)
    assert (
        sync(client, include_brain=True)["sections"]
        == sync(client, include_brain=True)["sections"]
    )


def test_query_mode_still_works(client, repo, vector_store):
    memory = seed(repo, "We use FastAPI.")
    vector_store.upsert(memory, FakeEmbedder().embed(memory.content))

    r = client.post(CONTEXT, json={"session_id": "s1", "query": "backend framework?"})
    assert r.status_code == 200
    assert [m["summary"] for m in r.json()["sections"]["relevant_memories"]] == ["We use FastAPI."]


@pytest.mark.parametrize(
    "bad",
    [
        {"session_id": "s1"},  # query mode (default) without query
        {"session_id": "s1", "mode": "query"},  # explicit query mode without query
        {"session_id": "s1", "mode": "sync", "query": "q"},  # sync must not carry a query
        {"session_id": "s1", "mode": "nonsense", "query": "q"},
    ],
)
def test_mode_validation(client, bad):
    assert client.post(CONTEXT, json=bad).status_code == 422


def test_sync_works_without_vector_index(client, repo, vector_store, monkeypatch):
    # Sync must not depend on Chroma at all — even a broken index can't stop it.
    def boom(*args, **kwargs):
        raise RuntimeError("index corrupted")

    monkeypatch.setattr(vector_store, "query", boom)
    seed(repo, "We use FastAPI.")
    assert [
        m["summary"] for m in sync(client, include_brain=True)["sections"]["relevant_memories"]
    ] == ["We use FastAPI."]


def test_sync_pack_leads_with_latest_project_state(repo, vector_store, db_conn):
    project_states = ProjectStateRepository(db_conn)
    project_states.save("proj_openmemory", "OpenMemory is a local-first continuity engine.", generated_from=[])
    pipeline = ContextPipeline(
        retrieval_engine=RetrievalEngine(FakeEmbedder(), vector_store, repo),
        ranking_engine=RankingEngine(),
        context_builder=ContextBuilder(),
        repository=repo,
        project_state_repository=project_states,
    )
    app = create_app()
    app.dependency_overrides[get_context_pipeline] = lambda: pipeline
    with TestClient(app) as client:
        pack = sync(client, project_id="proj_openmemory")

    assert pack["sections"]["project_state"] == "OpenMemory is a local-first continuity engine."


def test_sync_always_includes_rolling_conversation_summary(repo, vector_store, db_conn):
    # The rolling Current Context Summary is core task state, not brain
    # content — it must appear on sync even with include_brain=False.
    from app.models.domain.conversation_summary import ConversationSummary

    conversation_summaries = ConversationSummaryRepository(db_conn)
    conversation_summaries.save(ConversationSummary(session_id="s1", summary="Chose SQLite."))
    pipeline = ContextPipeline(
        retrieval_engine=RetrievalEngine(FakeEmbedder(), vector_store, repo),
        ranking_engine=RankingEngine(),
        context_builder=ContextBuilder(),
        repository=repo,
        conversation_summary_repository=conversation_summaries,
    )
    app = create_app()
    app.dependency_overrides[get_context_pipeline] = lambda: pipeline
    with TestClient(app) as client:
        pack = sync(client, include_brain=False)

    assert pack["sections"]["conversation_summary"] == "Chose SQLite."


def test_sync_falls_back_to_the_latest_other_session_summary_for_a_brand_new_chat(
    repo, vector_store, db_conn,
):
    # Cross-AI handoff: switching platforms (or opening a fresh chat) lands
    # on a session with no summary of its own — Sync there must still carry
    # forward the most recent OTHER session's summary, not come up empty.
    from app.models.domain.conversation_summary import ConversationSummary

    conversation_summaries = ConversationSummaryRepository(db_conn)
    conversation_summaries.save(
        ConversationSummary(session_id="chatgpt-a", summary="Decided SQLite, mid-refactor.")
    )
    pipeline = ContextPipeline(
        retrieval_engine=RetrievalEngine(FakeEmbedder(), vector_store, repo),
        ranking_engine=RankingEngine(),
        context_builder=ContextBuilder(),
        repository=repo,
        conversation_summary_repository=conversation_summaries,
    )
    app = create_app()
    app.dependency_overrides[get_context_pipeline] = lambda: pipeline
    with TestClient(app) as client:
        pack = sync(client, include_brain=False, session_id="claude-b")

    assert pack["sections"]["conversation_summary"] == "Decided SQLite, mid-refactor."


def test_sync_injects_the_latest_work_regardless_of_which_session_asks(
    repo, vector_store, db_conn,
):
    # Sync means "continue whatever I worked on last" — even a session with
    # its OWN summary must yield to a more recently updated one elsewhere.
    from app.models.domain.conversation_summary import ConversationSummary

    conversation_summaries = ConversationSummaryRepository(db_conn)
    conversation_summaries.save(
        ConversationSummary(session_id="gemini-c", summary="Old topic: TRACE-Lite.")
    )
    conversation_summaries.save(
        ConversationSummary(session_id="claude-b", summary="Latest topic: OpenMemory.")
    )
    pipeline = ContextPipeline(
        retrieval_engine=RetrievalEngine(FakeEmbedder(), vector_store, repo),
        ranking_engine=RankingEngine(),
        context_builder=ContextBuilder(),
        repository=repo,
        conversation_summary_repository=conversation_summaries,
    )
    app = create_app()
    app.dependency_overrides[get_context_pipeline] = lambda: pipeline
    with TestClient(app) as client:
        # A brand-new Gemini chat asks — but Claude's is the freshest work.
        pack = sync(client, include_brain=False, session_id="gemini-new")

    assert pack["sections"]["conversation_summary"] == "Latest topic: OpenMemory."
