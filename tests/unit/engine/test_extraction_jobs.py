"""Semantic extraction job: reads Workspace State (not raw episodes), gates
duplicates into reinforcement, empty-list bias, degrades cleanly."""

import pytest

from app.engine.llm.provider import ProviderError
from app.jobs.extraction_jobs import extract_semantic_memories
from app.memory.repositories.memory_repository import MemoryRepository
from app.models.domain.episode import Episode
from app.models.domain.workspace import Workspace
from app.models.enums import Confidence, MemoryCategory


class FakeProvider:
    def __init__(self, result=None, error=None):
        self._result, self._error = result, error
        self.prompts = []

    async def generate(self, prompt, output_schema):
        self.prompts.append(prompt)
        if self._error:
            raise ProviderError(self._error)
        return self._result

    async def health(self):  # pragma: no cover
        raise NotImplementedError


def workspace(internal_summary="Decided to use SQLite as the source of truth.", **overrides):
    return Workspace(project_id="proj_x", internal_summary=internal_summary, **overrides)


def episode(**overrides):
    defaults = dict(session_id="s1", project_id="proj_x", platform="chatgpt")
    return Episode(**{**defaults, **overrides})


async def test_stores_well_formed_candidates(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    provider = FakeProvider(
        result={
            "memories": [
                {
                    "type": "decision",
                    "content": "Chose SQLite over Postgres to keep OpenMemory fully local-first.",
                    "confidence": "high",
                }
            ]
        }
    )
    stored = await extract_semantic_memories(
        "proj_x", workspace(), episode(), memories, vector_store, embedding_service, provider
    )
    assert len(stored) == 1
    saved = memories.get(stored[0].id)
    assert saved.category is MemoryCategory.DECISION
    assert saved.confidence is Confidence.HIGH
    assert saved.project_id == "proj_x"
    assert saved.source.episode_id  # provenance carried


async def test_reads_workspace_state_not_raw_episode(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    provider = FakeProvider(result={"memories": []})
    ws = workspace(internal_summary="- distilled understanding of the project")
    await extract_semantic_memories(
        "proj_x", ws, episode(), memories, vector_store, embedding_service, provider
    )
    assert "distilled understanding" in provider.prompts[0]


async def test_near_duplicate_reinforces_instead_of_duplicating(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    content = "OpenMemory stores all data locally in SQLite; there is no cloud dependency."
    provider = FakeProvider(result={"memories": [{"type": "fact", "content": content, "confidence": "high"}]})

    first = await extract_semantic_memories(
        "proj_x", workspace(), episode(), memories, vector_store, embedding_service, provider
    )
    assert len(first) == 1

    second = await extract_semantic_memories(
        "proj_x", workspace(), episode(), memories, vector_store, embedding_service, provider
    )
    assert second == []  # reinforced, not re-inserted
    assert len(memories.list(project_id="proj_x")) == 1


async def test_empty_list_is_the_expected_common_outcome(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    provider = FakeProvider(result={"memories": []})
    stored = await extract_semantic_memories(
        "proj_x", workspace(), episode(), memories, vector_store, embedding_service, provider
    )
    assert stored == []


async def test_invalid_candidates_are_dropped_silently(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    provider = FakeProvider(
        result={
            "memories": [
                {"type": "not-a-real-type", "content": "junk", "confidence": "high"},
                {"type": "fact", "content": "   ", "confidence": "high"},
                {"type": "fact", "content": "ok", "confidence": "not-a-confidence"},
            ]
        }
    )
    stored = await extract_semantic_memories(
        "proj_x", workspace(), episode(), memories, vector_store, embedding_service, provider
    )
    assert stored == []


async def test_provider_failure_yields_no_extraction(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    provider = FakeProvider(error="down")
    stored = await extract_semantic_memories(
        "proj_x", workspace(), episode(), memories, vector_store, embedding_service, provider
    )
    assert stored == []


async def test_no_provider_skips_extraction(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    stored = await extract_semantic_memories(
        "proj_x", workspace(), episode(), memories, vector_store, embedding_service, None
    )
    assert stored == []


async def test_empty_workspace_skips_extraction(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    provider = FakeProvider(result={"memories": []})
    stored = await extract_semantic_memories(
        "proj_x", workspace(internal_summary=""), episode(), memories, vector_store, embedding_service, provider
    )
    assert stored == []
    assert provider.prompts == []  # never called the model for nothing
