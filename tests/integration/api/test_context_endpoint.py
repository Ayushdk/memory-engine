"""POST /api/v1/context — the full retrieval slice over real SQLite + Chroma,
seeded through the real ingestion pipeline, with the deterministic fake embedder."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_context_pipeline, get_ingestion_pipeline
from app.engine.context.context_builder import ContextBuilder
from app.engine.orchestrator.context_pipeline import ContextPipeline
from app.engine.retrieval.ranking_engine import RankingEngine
from app.engine.retrieval.retrieval_engine import RetrievalEngine
from app.main import create_app
from app.memory.repositories.memory_repository import MemoryRepository
from tests.integration.test_ingestion_pipeline import FakeEmbedder, pipeline  # noqa: F401

CONTEXT = "/api/v1/context"
INGEST = "/api/v1/ingest"


@pytest.fixture
def repo(db_conn):
    return MemoryRepository(db_conn)


@pytest.fixture
def client(pipeline, repo, vector_store):  # noqa: F811
    context_pipeline = ContextPipeline(
        retrieval_engine=RetrievalEngine(FakeEmbedder(), vector_store, repo),
        ranking_engine=RankingEngine(),
        context_builder=ContextBuilder(),
        repository=repo,
    )
    app = create_app()
    app.dependency_overrides[get_ingestion_pipeline] = lambda: pipeline
    app.dependency_overrides[get_context_pipeline] = lambda: context_pipeline
    with TestClient(app) as client:
        yield client


def ingest(client, content, project_id="proj_x"):
    r = client.post(
        INGEST,
        json={
            "session_id": "s1",
            "platform": "chatgpt",
            "role": "user",
            "content": content,
            "project_id": project_id,
        },
    )
    assert r.status_code == 200
    return r.json()


def get_context(client, query="what did we decide?", project_id=None):
    r = client.post(CONTEXT, json={"session_id": "s1", "query": query, "project_id": project_id})
    assert r.status_code == 200
    return r.json()


def test_normal_retrieval(client):
    ingest(client, "We decided to use SQLite as the source of truth.")
    ingest(client, "I prefer diagrams over long text.", project_id=None)

    pack = get_context(client)
    assert pack["session_id"] == "s1"
    assert pack["token_estimate"] > 0
    summaries = [m["summary"] for m in pack["sections"]["relevant_memories"]]
    assert summaries == ["We decided to use SQLite as the source of truth."]
    assert pack["sections"]["profile"] == ["I prefer diagrams over long text."]
    assert pack["sections"]["project_state"] is None  # Phase 5 fills this


def test_empty_retrieval(client):
    pack = get_context(client)
    assert pack["sections"]["relevant_memories"] == []
    assert pack["sections"]["profile"] == []
    assert pack["sections"]["open_questions"] == []
    assert pack["token_estimate"] == 0


def test_project_filtering(client):
    ingest(client, "We decided to use SQLite here.", project_id="proj_x")
    ingest(client, "We decided to use Postgres there.", project_id="proj_y")

    summaries = [
        m["summary"]
        for m in get_context(client, project_id="proj_x")["sections"]["relevant_memories"]
    ]
    assert summaries == ["We decided to use SQLite here."]


def test_open_questions_section(client):
    ingest(client, "Which cache should we pick?")
    pack = get_context(client)
    assert pack["sections"]["open_questions"] == ["Which cache should we pick?"]
    assert pack["sections"]["relevant_memories"] == []


def test_access_bookkeeping_for_selected_only(client, repo):
    selected = ingest(client, "We decided to use SQLite here.", project_id="proj_x")
    excluded = ingest(client, "We decided to use Postgres there.", project_id="proj_y")

    get_context(client, project_id="proj_x")

    hit = repo.get(selected["memory_id"])
    assert hit.access_count == 1
    assert hit.last_accessed_at is not None
    miss = repo.get(excluded["memory_id"])
    assert miss.access_count == 0
    assert miss.last_accessed_at is None


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"session_id": "s1"},  # no query
        {"session_id": "s1", "query": ""},  # empty query
        {"session_id": "", "query": "q"},  # empty session
    ],
)
def test_invalid_requests_are_422(client, bad):
    assert client.post(CONTEXT, json=bad).status_code == 422


def test_token_budget_trimming(client, monkeypatch):
    from app.core.config import get_settings

    contents = [f"We decided to use component {'x' * 200} number {i}." for i in range(4)]
    for content in contents:
        ingest(client, content)
    budget = (len(contents[0]) // 4) * 2  # room for ~2 memories
    monkeypatch.setattr(get_settings(), "context_token_budget", budget, raising=True)

    pack = get_context(client)
    assert 0 < len(pack["sections"]["relevant_memories"]) < 4
    assert pack["token_estimate"] <= budget


def test_deterministic_responses(client):
    ingest(client, "We decided to use SQLite here.")
    ingest(client, "We decided to use ULID identifiers.")

    first = get_context(client)
    second = get_context(client)
    assert first["sections"] == second["sections"]
    assert first["token_estimate"] == second["token_estimate"]
