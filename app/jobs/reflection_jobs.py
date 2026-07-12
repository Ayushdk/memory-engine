"""Reflection — the Project Brain's quality guardian (intelligence-layer.md
§7). Runs after extraction, on the reasoner model: merges duplicates,
resolves contradictions/supersession, strengthens weak-but-corroborated
memories, then synthesizes a new Project State version from what remains.

Deterministic shortlist, LLM confirms: embedding similarity clusters
candidate near-duplicates/contradictions (a cheap, always-safe pass); only
clusters are ever sent to the model. No clusters, no model call — most
reflection cycles are a no-op, by design (quality over quantity applies to
compute too, not just storage).
"""

from dataclasses import dataclass

from loguru import logger

from app.core.config import get_settings
from app.engine.llm.provider import LLMProvider, ProviderError
from app.memory.repositories.memory_relation_repository import MemoryRelationRepository
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.project_state_repository import ProjectStateRepository
from app.memory.vector.chroma_client import ChromaVectorStore, active_where
from app.models.domain.memory import Memory
from app.models.enums import Confidence, MemoryCategory, MemoryStatus, MemoryView
from app.services.embedding_service import EmbeddingService

MAX_CLUSTER_SIZE = 4

CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["merge", "supersede", "strengthen", "keep"]},
        "target_id": {"type": "string"},  # strengthen: memory to bump; supersede: memory to keep
        "superseded_id": {"type": "string"},  # supersede: memory to retire
        "merged_content": {"type": "string"},  # merge: self-contained combined content
    },
    "required": ["action"],
}

CLUSTER_PROMPT = """You are reviewing a small cluster of a project's stored \
knowledge that looked similar enough to need a human-quality judgment call. \
Decide exactly one action:

- "merge": these are the same fact/decision stated differently. Return \
merged_content — a single, self-contained version that keeps everything \
true from all of them. Uses the first listed id as the survivor.
- "supersede": one is outdated or contradicted by a newer one. Return \
target_id (the one to keep) and superseded_id (the one to retire).
- "strengthen": they corroborate each other but aren't the same statement — \
keep both, but the knowledge is now better evidenced. Return target_id (the \
best-formed one) to raise its confidence.
- "keep": genuinely distinct; do nothing.

When unsure, prefer "keep" — do not merge or retire memories on a guess.

Memories:
{items}
"""

STATE_SCHEMA = {
    "type": "object",
    "properties": {"content": {"type": "string"}},
    "required": ["content"],
}

STATE_PROMPT = """Synthesize a current-state overview of this project from \
its highest-confidence active knowledge below. Write it for someone with no \
other context: what the project is, key decisions and why, constraints, \
open questions. Be concise and self-contained — this replaces re-reading \
everything below, it does not summarize prose, it distills facts.

Knowledge:
{items}
"""


@dataclass
class ReflectionSummary:
    merged: int = 0
    superseded: int = 0
    strengthened: int = 0


def _format_items(memories: list[Memory]) -> str:
    return "\n".join(f"- id={m.id} ({m.category.value}, {m.confidence.value}): {m.content}" for m in memories)


def _cluster_active_memories(
    active: list[Memory], vector_store: ChromaVectorStore, embeddings: EmbeddingService, project_id: str
) -> list[list[Memory]]:
    threshold = get_settings().update_similarity_threshold
    by_id = {m.id: m for m in active}
    visited: set[str] = set()
    clusters: list[list[Memory]] = []

    for memory in active:
        if memory.id in visited:
            continue
        neighbors = vector_store.query(
            embeddings.embed(memory.content), n_results=MAX_CLUSTER_SIZE, where=active_where(project_id)
        )
        cluster = [memory]
        visited.add(memory.id)
        for neighbor_id, similarity in neighbors:
            if neighbor_id == memory.id or neighbor_id in visited or similarity < threshold:
                continue
            candidate = by_id.get(neighbor_id)
            if candidate is None:  # not a project-scoped active memory we loaded
                continue
            cluster.append(candidate)
            visited.add(neighbor_id)
            if len(cluster) >= MAX_CLUSTER_SIZE:
                break
        if len(cluster) >= 2:
            clusters.append(cluster)

    return clusters


def _apply_action(
    cluster: list[Memory],
    result: dict,
    memories: MemoryRepository,
    vector_store: ChromaVectorStore,
    relations: MemoryRelationRepository,
    embeddings: EmbeddingService,
) -> str | None:
    by_id = {m.id: m for m in cluster}
    action = result.get("action")

    if action == "merge":
        content = (result.get("merged_content") or "").strip()
        if not content:
            return None
        survivor = cluster[0]
        updated = survivor.model_copy(update={"content": content})
        memories.save(updated)
        vector_store.upsert(updated, embeddings.embed(content))
        for other in cluster[1:]:
            memories.set_status(other.id, MemoryStatus.MERGED)
            vector_store.update_status(other.id, MemoryStatus.MERGED.value)
            relations.link(survivor.id, other.id, "merged_from")
        return "merged"

    if action == "supersede":
        target_id, superseded_id = result.get("target_id"), result.get("superseded_id")
        if target_id not in by_id or superseded_id not in by_id or target_id == superseded_id:
            return None
        memories.set_status(superseded_id, MemoryStatus.SUPERSEDED)
        vector_store.update_status(superseded_id, MemoryStatus.SUPERSEDED.value)
        relations.link(target_id, superseded_id, "supersedes")
        return "superseded"

    if action == "strengthen":
        target_id = result.get("target_id")
        if target_id not in by_id:
            return None
        memories.touch(target_id, confidence=Confidence.HIGH)
        return "strengthened"

    return None  # "keep" or unrecognized — no-op


async def reflect_project(
    project_id: str,
    memories: MemoryRepository,
    vector_store: ChromaVectorStore,
    embeddings: EmbeddingService,
    relations: MemoryRelationRepository,
    provider: LLMProvider | None,
) -> ReflectionSummary:
    summary = ReflectionSummary()
    if provider is None:
        return summary

    active = memories.list(view=MemoryView.PROJECT, project_id=project_id, status=MemoryStatus.ACTIVE)
    if len(active) < 2:
        return summary

    clusters = _cluster_active_memories(active, vector_store, embeddings, project_id)
    for cluster in clusters:
        prompt = CLUSTER_PROMPT.format(items=_format_items(cluster))
        try:
            result = await provider.generate(prompt, CLUSTER_SCHEMA)
        except ProviderError as exc:
            logger.warning("Reflection cluster review failed for project {}: {}", project_id, exc)
            continue
        outcome = _apply_action(cluster, result, memories, vector_store, relations, embeddings)
        if outcome == "merged":
            summary.merged += 1
        elif outcome == "superseded":
            summary.superseded += 1
        elif outcome == "strengthened":
            summary.strengthened += 1

    if summary.merged or summary.superseded or summary.strengthened:
        logger.info(
            "Reflection for {}: {} merged, {} superseded, {} strengthened",
            project_id,
            summary.merged,
            summary.superseded,
            summary.strengthened,
        )
    return summary


async def synthesize_project_state(
    project_id: str,
    memories: MemoryRepository,
    project_states: ProjectStateRepository,
    provider: LLMProvider | None,
) -> None:
    if provider is None:
        return

    active = memories.list(view=MemoryView.PROJECT, project_id=project_id, status=MemoryStatus.ACTIVE)
    if not active:
        return

    prompt = STATE_PROMPT.format(items=_format_items(active))
    try:
        result = await provider.generate(prompt, STATE_SCHEMA)
    except ProviderError as exc:
        logger.warning("Project state synthesis failed for project {}: {}", project_id, exc)
        return

    content = (result.get("content") or "").strip()
    if not content:
        return

    state = project_states.save(project_id, content, generated_from=[m.id for m in active])
    logger.info("Project state v{} synthesized for {}", state.version, project_id)


def promote_to_personal_brain(
    project_id: str,
    memories: MemoryRepository,
    vector_store: ChromaVectorStore,
    embeddings: EmbeddingService,
    relations: MemoryRelationRepository,
) -> int:
    """Personal Brain is a promotion target, not an extraction target
    (intelligence-layer.md §7.1) — no LLM call here, just a deterministic
    threshold gate on knowledge that has already proven durable in the
    Project Brain. Only `preference` memories qualify: the one category
    that means "how the user likes to work" rather than a project fact."""
    threshold = get_settings().personal_brain_promotion_threshold
    candidates = memories.list(
        view=MemoryView.PROJECT,
        project_id=project_id,
        category=MemoryCategory.PREFERENCE,
        status=MemoryStatus.ACTIVE,
    )
    promoted = 0
    for candidate in candidates:
        if candidate.confidence is not Confidence.HIGH:
            continue
        if candidate.reinforcement_count < threshold:
            continue
        if relations.has_relation(candidate.id, "promoted_from"):
            continue

        embedding = embeddings.embed(candidate.content)
        existing_id = None
        for neighbor_id, similarity in vector_store.query(embedding, n_results=5, where=active_where()):
            if neighbor_id == candidate.id or similarity < get_settings().update_similarity_threshold:
                continue
            profile_match = memories.get(neighbor_id)
            if profile_match and profile_match.view is MemoryView.PROFILE:
                existing_id = profile_match.id
                break

        if existing_id:
            memories.touch(existing_id, confidence=Confidence.HIGH)
            relations.link(existing_id, candidate.id, "promoted_from")
        else:
            profile_memory = Memory(
                content=candidate.content,
                summary=candidate.summary,
                category=candidate.category,
                view=MemoryView.PROFILE,
                project_id=None,
                importance=candidate.importance,
                confidence=Confidence.HIGH,
                source=candidate.source,
            )
            memories.save(profile_memory)
            vector_store.upsert(profile_memory, embeddings.embed(profile_memory.content))
            relations.link(profile_memory.id, candidate.id, "promoted_from")

        promoted += 1

    if promoted:
        logger.info("Promoted {} preference(s) to Personal Brain from {}", promoted, project_id)
    return promoted
