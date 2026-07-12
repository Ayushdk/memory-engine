"""Reflection: deterministic clustering shortlists, LLM confirms the action,
repository applies it. No cluster means no model call — that's the common
case and must stay cheap."""

import re

from tests.conftest import make_memory

from app.engine.llm.provider import ProviderError
from app.jobs.reflection_jobs import promote_to_personal_brain, reflect_project, synthesize_project_state
from app.memory.repositories.memory_relation_repository import MemoryRelationRepository
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.project_state_repository import ProjectStateRepository
from app.models.enums import Confidence, MemoryCategory, MemoryStatus, MemoryView


class FakeProvider:
    def __init__(self, action="keep", content=None, error=None):
        self.action, self.content, self._error = action, content, error
        self.prompts = []

    async def generate(self, prompt, output_schema):
        self.prompts.append(prompt)
        if self._error:
            raise ProviderError(self._error)
        if self.content is not None:  # synthesize_project_state call
            return {"content": self.content}
        ids = re.findall(r"id=(\S+)", prompt)
        if self.action == "merge":
            return {"action": "merge", "merged_content": "Combined: local-first, SQLite, no cloud dependency."}
        if self.action == "supersede":
            return {"action": "supersede", "target_id": ids[0], "superseded_id": ids[1]}
        if self.action == "strengthen":
            return {"action": "strengthen", "target_id": ids[0]}
        return {"action": "keep"}

    async def health(self):  # pragma: no cover
        raise NotImplementedError


def _seed_near_duplicates(memories: MemoryRepository, vector_store, embeddings, **overrides):
    a = make_memory(id="mem_a", content="OpenMemory stores everything locally in SQLite.", **overrides)
    b = make_memory(id="mem_b", content="OpenMemory stores all data locally in SQLite.", **overrides)
    for m in (a, b):
        memories.save(m)
        vector_store.upsert(m, embeddings.embed(m.content))
    return a, b


async def test_fewer_than_two_active_memories_skips_llm(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    memories.save(make_memory())
    provider = FakeProvider()

    summary = await reflect_project("proj_openmemory", memories, vector_store, embedding_service, relations, provider)

    assert summary.merged == summary.superseded == summary.strengthened == 0
    assert provider.prompts == []


async def test_dissimilar_memories_form_no_cluster(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    a = make_memory(id="mem_a", content="Selected FastAPI over Flask for the backend.")
    b = make_memory(id="mem_b", content="The user prefers small, incremental commits.")
    for m in (a, b):
        memories.save(m)
        vector_store.upsert(m, embedding_service.embed(m.content))
    provider = FakeProvider()

    summary = await reflect_project("proj_openmemory", memories, vector_store, embedding_service, relations, provider)

    assert summary.merged == summary.superseded == summary.strengthened == 0
    assert provider.prompts == []


async def test_merge_near_duplicates(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    a, b = _seed_near_duplicates(memories, vector_store, embedding_service)
    provider = FakeProvider(action="merge")

    summary = await reflect_project("proj_openmemory", memories, vector_store, embedding_service, relations, provider)

    assert summary.merged == 1
    statuses = {memories.get(a.id).status, memories.get(b.id).status}
    assert statuses == {MemoryStatus.ACTIVE, MemoryStatus.MERGED}
    active = [m for m in (memories.get(a.id), memories.get(b.id)) if m.status is MemoryStatus.ACTIVE]
    assert active[0].content == "Combined: local-first, SQLite, no cloud dependency."


async def test_supersede_near_duplicates(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    a, b = _seed_near_duplicates(memories, vector_store, embedding_service)
    provider = FakeProvider(action="supersede")

    summary = await reflect_project("proj_openmemory", memories, vector_store, embedding_service, relations, provider)

    assert summary.superseded == 1
    statuses = {memories.get(a.id).status, memories.get(b.id).status}
    assert statuses == {MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED}


async def test_strengthen_near_duplicates(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    a, b = _seed_near_duplicates(memories, vector_store, embedding_service, confidence=Confidence.MEDIUM)
    provider = FakeProvider(action="strengthen")

    summary = await reflect_project("proj_openmemory", memories, vector_store, embedding_service, relations, provider)

    assert summary.strengthened == 1
    assert memories.get(a.id).status is MemoryStatus.ACTIVE
    assert memories.get(b.id).status is MemoryStatus.ACTIVE
    assert Confidence.HIGH in (memories.get(a.id).confidence, memories.get(b.id).confidence)


async def test_keep_action_changes_nothing(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    a, b = _seed_near_duplicates(memories, vector_store, embedding_service)
    provider = FakeProvider(action="keep")

    summary = await reflect_project("proj_openmemory", memories, vector_store, embedding_service, relations, provider)

    assert summary.merged == summary.superseded == summary.strengthened == 0
    assert memories.get(a.id).status is MemoryStatus.ACTIVE
    assert memories.get(b.id).status is MemoryStatus.ACTIVE


async def test_no_provider_skips_reflection(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    _seed_near_duplicates(memories, vector_store, embedding_service)

    summary = await reflect_project("proj_openmemory", memories, vector_store, embedding_service, relations, None)

    assert summary.merged == summary.superseded == summary.strengthened == 0


async def test_provider_failure_on_a_cluster_is_swallowed(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    a, b = _seed_near_duplicates(memories, vector_store, embedding_service)
    provider = FakeProvider(error="down")

    summary = await reflect_project("proj_openmemory", memories, vector_store, embedding_service, relations, provider)

    assert summary.merged == summary.superseded == summary.strengthened == 0
    assert memories.get(a.id).status is MemoryStatus.ACTIVE
    assert memories.get(b.id).status is MemoryStatus.ACTIVE


async def test_synthesize_project_state_saves_new_version(db_conn):
    memories = MemoryRepository(db_conn)
    project_states = ProjectStateRepository(db_conn)
    saved = make_memory()
    memories.save(saved)
    provider = FakeProvider(content="OpenMemory is a local-first continuity engine.")

    await synthesize_project_state("proj_openmemory", memories, project_states, provider)

    state = project_states.latest("proj_openmemory")
    assert state is not None
    assert state.version == 1
    assert state.content == "OpenMemory is a local-first continuity engine."
    assert state.generated_from == [saved.id]


async def test_synthesize_project_state_skips_when_no_active_memories(db_conn):
    memories = MemoryRepository(db_conn)
    project_states = ProjectStateRepository(db_conn)
    provider = FakeProvider(content="anything")

    await synthesize_project_state("proj_openmemory", memories, project_states, provider)

    assert project_states.latest("proj_openmemory") is None


async def test_synthesize_project_state_skips_without_provider(db_conn):
    memories = MemoryRepository(db_conn)
    project_states = ProjectStateRepository(db_conn)
    memories.save(make_memory())

    await synthesize_project_state("proj_openmemory", memories, project_states, None)

    assert project_states.latest("proj_openmemory") is None


def _preference(memories: MemoryRepository, vector_store, embeddings, **overrides):
    defaults = dict(
        id="mem_pref",
        content="The user prefers small, incremental commits.",
        category=MemoryCategory.PREFERENCE,
        confidence=Confidence.HIGH,
        reinforcement_count=3,
    )
    m = make_memory(**{**defaults, **overrides})
    memories.save(m)
    vector_store.upsert(m, embeddings.embed(m.content))
    return m


def test_promotion_skips_below_reinforcement_threshold(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    _preference(memories, vector_store, embedding_service, reinforcement_count=1)

    promoted = promote_to_personal_brain("proj_openmemory", memories, vector_store, embedding_service, relations)

    assert promoted == 0
    assert memories.list(view=MemoryView.PROFILE) == []


def test_promotion_skips_non_preference_category(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    _preference(memories, vector_store, embedding_service, category=MemoryCategory.DECISION)

    promoted = promote_to_personal_brain("proj_openmemory", memories, vector_store, embedding_service, relations)

    assert promoted == 0


def test_promotion_creates_profile_memory(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    pref = _preference(memories, vector_store, embedding_service)

    promoted = promote_to_personal_brain("proj_openmemory", memories, vector_store, embedding_service, relations)

    assert promoted == 1
    profile = memories.list(view=MemoryView.PROFILE)
    assert len(profile) == 1
    assert profile[0].content == pref.content
    assert profile[0].project_id is None
    # original PROJECT memory is untouched, just linked
    assert memories.get(pref.id).view is MemoryView.PROJECT
    assert relations.has_relation(pref.id, "promoted_from")


def test_promotion_is_idempotent(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    _preference(memories, vector_store, embedding_service)

    first = promote_to_personal_brain("proj_openmemory", memories, vector_store, embedding_service, relations)
    second = promote_to_personal_brain("proj_openmemory", memories, vector_store, embedding_service, relations)

    assert first == 1
    assert second == 0
    assert len(memories.list(view=MemoryView.PROFILE)) == 1


def test_promotion_reinforces_existing_profile_match_instead_of_duplicating(db_conn, vector_store, embedding_service):
    memories = MemoryRepository(db_conn)
    relations = MemoryRelationRepository(db_conn)
    existing = make_memory(
        id="mem_profile_existing",
        content="The user prefers small, incremental commits.",
        category=MemoryCategory.PREFERENCE,
        view=MemoryView.PROFILE,
        project_id=None,
        confidence=Confidence.HIGH,
    )
    memories.save(existing)
    vector_store.upsert(existing, embedding_service.embed(existing.content))
    pref = _preference(memories, vector_store, embedding_service, content="The user prefers small, incremental commits.")

    promoted = promote_to_personal_brain("proj_openmemory", memories, vector_store, embedding_service, relations)

    assert promoted == 1
    assert len(memories.list(view=MemoryView.PROFILE)) == 1
    assert relations.has_relation(pref.id, "promoted_from")
