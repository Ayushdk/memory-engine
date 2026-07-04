"""Ingestion Orchestrator tests: real SQLite + real embedded Chroma, with a
deterministic fake embedder so similarity (the UPDATE confirmation) is
controllable without loading MiniLM."""

import hashlib
import math

import pytest

from app.engine.classifier.memory_classifier import RuleClassifier
from app.engine.orchestrator.ingestion_pipeline import IngestionPipeline
from app.engine.router.storage_router import RuleStorageRouter
from app.engine.scorer.importance_scorer import RuleImportanceScorer
from app.engine.working_memory.persistence import PersistentWorkingMemory
from app.engine.working_memory.working_memory_manager import WorkingMemoryManager
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.session_repository import SessionRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from app.models.enums import ClassifierAction, MemoryCategory, MemoryStatus, MemoryView

FLASK_MSG = "We'll use Flask for the backend."
FASTAPI_MSG = "We switched to FastAPI for the backend."


class FakeEmbedder:
    """Deterministic unit vectors; texts in the same group share a vector."""

    GROUPS = {FLASK_MSG: "backend", FASTAPI_MSG: "backend"}

    def embed(self, text: str) -> list[float]:
        seed = hashlib.sha256(self.GROUPS.get(text, text).encode()).digest()
        vec = [b - 127.5 for b in seed]  # 32 dims: unrelated texts stay dissimilar
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec]


@pytest.fixture
def pipeline(db_conn, vector_store):
    return IngestionPipeline(
        working_memory=PersistentWorkingMemory(
            WorkingMemoryManager(capacity=5),
            WorkingMemoryRepository(db_conn),
            SessionRepository(db_conn),
        ),
        classifier=RuleClassifier(),
        scorer=RuleImportanceScorer(),
        router=RuleStorageRouter(),
        repository=MemoryRepository(db_conn),
        vector_store=vector_store,
        embedding_service=FakeEmbedder(),
    )


def ingest(pipeline, content, project_id="proj_x"):
    return pipeline.ingest("s1", "chatgpt", "user", content, project_id)


def test_ignore_exits_early(pipeline, db_conn, vector_store):
    result = ingest(pipeline, "Thanks!")

    assert result.action is ClassifierAction.IGNORE
    assert result.success is True
    assert result.synchronization_status == "skipped"
    assert result.memory_id is None
    assert result.scoring is None and result.routing is None  # never scored/routed
    assert MemoryRepository(db_conn).list(status=None) == []
    assert vector_store.count() == 0
    # but the message still landed in working memory
    assert pipeline._working_memory.get_messages("s1")[0].content == "Thanks!"


def test_store_writes_sqlite_and_chroma(pipeline, db_conn, vector_store):
    result = ingest(pipeline, FLASK_MSG)

    assert result.success is True
    assert result.action is ClassifierAction.STORE
    assert result.synchronization_status == "in_sync"

    stored = MemoryRepository(db_conn).get(result.memory_id)
    assert stored.category is MemoryCategory.DECISION
    assert stored.view is MemoryView.PROJECT
    assert stored.importance == result.scoring.importance
    assert stored.source.platform == "chatgpt"
    assert vector_store.count() == 1


def test_update_supersedes_similar_memory(pipeline, db_conn, vector_store):
    old = ingest(pipeline, FLASK_MSG)
    new = ingest(pipeline, FASTAPI_MSG)  # same fake vector → similarity 1.0 > 0.85

    assert new.action is ClassifierAction.UPDATE
    repo = MemoryRepository(db_conn)
    assert repo.get(new.memory_id).supersedes == old.memory_id
    assert repo.get(old.memory_id).status is MemoryStatus.SUPERSEDED
    assert new.memory_id != old.memory_id  # non-destructive: both rows exist
    # superseded memory no longer matches active-filtered vector queries
    active = vector_store.query(
        FakeEmbedder().embed(FASTAPI_MSG), n_results=2, where={"status": "active"}
    )
    assert [mid for mid, _ in active] == [new.memory_id]


def test_unconfirmed_update_stores_as_new(pipeline, db_conn):
    ingest(pipeline, "I decided to use ULID identifiers.")  # unrelated vector
    result = ingest(pipeline, FASTAPI_MSG)

    assert result.action is ClassifierAction.UPDATE
    assert result.reasoning == "stored as new memory"
    repo = MemoryRepository(db_conn)
    assert repo.get(result.memory_id).supersedes is None
    assert len(repo.list()) == 2  # nothing superseded


def test_sqlite_failure_prevents_chroma_write(pipeline, vector_store, monkeypatch):
    def boom(memory):
        raise RuntimeError("disk full")

    monkeypatch.setattr(pipeline._repository, "save", boom)
    result = ingest(pipeline, FLASK_MSG)

    assert result.success is False
    assert result.synchronization_status == "failed"
    assert result.memory_id is None
    assert "disk full" in result.reasoning
    assert vector_store.count() == 0  # Chroma never written


def test_chroma_failure_leaves_sqlite_intact(pipeline, db_conn, monkeypatch):
    def boom(memory, embedding):
        raise RuntimeError("index corrupted")

    monkeypatch.setattr(pipeline._vector_store, "upsert", boom)
    result = ingest(pipeline, FLASK_MSG)

    assert result.success is True  # source of truth is correct
    assert result.synchronization_status == "sqlite_only"
    assert MemoryRepository(db_conn).get(result.memory_id) is not None


def test_delete_and_merge_commands_are_not_stored(pipeline, db_conn):
    for message, action in [
        ("Delete the memory about Flask.", ClassifierAction.DELETE),
        ("Merge the two FastAPI memories.", ClassifierAction.MERGE),
    ]:
        result = ingest(pipeline, message)
        assert result.action is action
        assert result.synchronization_status == "skipped"
    assert MemoryRepository(db_conn).list(status=None) == []


def test_result_carries_full_trace(pipeline):
    result = ingest(pipeline, FLASK_MSG)
    assert result.classification.matched_rule == "decision"
    assert result.scoring.base_score == 9
    assert result.routing.matched_rule == "has_project"
