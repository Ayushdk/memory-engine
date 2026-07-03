"""Candidate Retrieval Engine: real SQLite + Chroma, deterministic fake embedder."""

import pytest

from app.engine.retrieval.retrieval_engine import RetrievalEngine, RetrievalResult
from app.memory.repositories.memory_repository import MemoryRepository
from app.models.domain.memory import Memory
from app.models.enums import MemoryStatus
from tests.conftest import make_memory
from tests.integration.test_ingestion_pipeline import FakeEmbedder


@pytest.fixture
def repo(db_conn):
    return MemoryRepository(db_conn)


@pytest.fixture
def engine(repo, vector_store):
    return RetrievalEngine(FakeEmbedder(), vector_store, repo)


def seed(repo, vector_store, memory: Memory):
    repo.save(memory)
    vector_store.upsert(memory, FakeEmbedder().embed(memory.content))
    return memory


def test_retrieval_without_project_filter(engine, repo, vector_store):
    a = seed(repo, vector_store, make_memory(content="fact a", project_id="proj_x"))
    b = seed(repo, vector_store, make_memory(content="fact b", project_id="proj_y"))

    result = engine.retrieve("anything")
    assert set(result.candidate_memory_ids) == {a.id, b.id}


def test_retrieval_with_project_filter(engine, repo, vector_store):
    a = seed(repo, vector_store, make_memory(content="fact a", project_id="proj_x"))
    seed(repo, vector_store, make_memory(content="fact b", project_id="proj_y"))

    result = engine.retrieve("anything", project_id="proj_x")
    assert result.candidate_memory_ids == [a.id]


def test_only_active_memories(engine, repo, vector_store):
    active = seed(repo, vector_store, make_memory(content="current"))
    old = seed(repo, vector_store, make_memory(content="old"))
    repo.set_status(old.id, MemoryStatus.SUPERSEDED)
    vector_store.update_status(old.id, "superseded")

    result = engine.retrieve("anything")
    assert result.candidate_memory_ids == [active.id]


def test_empty_store(engine):
    result = engine.retrieve("anything")
    assert result.candidate_memory_ids == []
    assert result.retrieved_memories == []
    assert result.query_embedding  # embedding is still produced


def test_top_k_limits_candidates(engine, repo, vector_store):
    for i in range(5):
        seed(repo, vector_store, make_memory(content=f"fact {i}"))

    assert len(engine.retrieve("anything", top_k=3).retrieved_memories) == 3
    assert len(engine.retrieve("anything").retrieved_memories) == 5  # default 40 covers all


def test_result_structure_and_no_ranking(engine, repo, vector_store):
    seeded = seed(repo, vector_store, make_memory(content="fact a"))

    result = engine.retrieve("fact a")
    assert isinstance(result, RetrievalResult)
    assert result.candidate_memory_ids == [seeded.id]
    assert result.retrieved_memories[0] == seeded  # full Memory objects from SQLite
    assert result.retrieval_metadata["requested_top_k"] == 40
    # similarity per candidate is exposed for the ranking engine, unmodified
    assert result.retrieval_metadata["similarities"][seeded.id] == pytest.approx(1.0)
    # retrieval performs no access bookkeeping — that belongs to later stages
    assert engine._repository.get(seeded.id).access_count == 0


def test_stale_index_ids_are_dropped(engine, repo, vector_store):
    ghost = make_memory(content="ghost")
    vector_store.upsert(ghost, FakeEmbedder().embed(ghost.content))  # in Chroma, not SQLite

    result = engine.retrieve("anything")
    assert result.candidate_memory_ids == []
