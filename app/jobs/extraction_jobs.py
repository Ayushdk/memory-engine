"""Semantic extraction job — reasoner model, evolves the Project Brain from
the Workspace's current understanding rather than re-reading raw episodes.

Episodes are evidence (provenance only, via Source.episode_id); Workspace
State is the distilled understanding extraction actually reads. This keeps
the semantic layer from depending on reprocessing raw conversation.

LLM proposes, deterministic code disposes: schema-validated candidates are
gated by embedding similarity — a near-match reinforces the existing memory
(recency + confidence bump) instead of duplicating it. Provider absent or
failing means no extraction this cycle; Project Brain growth just pauses,
never on invented data.
"""

from loguru import logger

from app.core.config import get_settings
from app.engine.llm.provider import LLMProvider, ProviderError
from app.engine.scorer.scoring_policy import BASE_SCORES
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.vector.chroma_client import ChromaVectorStore, active_where
from app.models.domain.episode import Episode
from app.models.domain.memory import Memory, Source
from app.models.domain.workspace import Workspace
from app.models.enums import Confidence, MemoryCategory, MemoryView
from app.services.embedding_service import EmbeddingService

EXTRACT_TYPES = ("decision", "constraint", "fact", "preference", "insight", "open_question", "idea")

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(EXTRACT_TYPES)},
                    "content": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["type", "content", "confidence"],
            },
        }
    },
    "required": ["memories"],
}

PROMPT_TEMPLATE = """You extract durable, self-contained knowledge for a \
project's long-term memory (the "Project Brain") from the current working \
understanding of a project.

Each memory you return must be understandable on its own, months later, \
without the original conversation. Strongly prefer returning FEWER, \
higher-quality memories over many marginal ones. If nothing durable and \
self-contained emerges, return an empty list — this is the expected outcome \
most of the time, not a failure. When uncertain, do not create a memory.

Types:
- decision: a choice made, with alternatives considered and why they lost
- constraint: a hard must/must-not rule
- fact: a stable truth about the project or user
- preference: how the user likes to work
- insight: a reasoning or trade-off worth remembering
- open_question: an unresolved thread
- idea: a deliberately deferred proposal

Current working understanding of the project:
{workspace_state}

Current goal: {goal}
Current blockers: {blockers}
"""


def _importance_for(category: MemoryCategory) -> int:
    return BASE_SCORES.get(category, 5)


async def extract_semantic_memories(
    project_id: str,
    workspace: Workspace,
    episode: Episode,
    memories: MemoryRepository,
    vector_store: ChromaVectorStore,
    embeddings: EmbeddingService,
    provider: LLMProvider | None,
) -> list[Memory]:
    if provider is None or not workspace.internal_summary.strip():
        return []

    prompt = PROMPT_TEMPLATE.format(
        workspace_state=workspace.internal_summary,
        goal=workspace.goal or "none stated",
        blockers=", ".join(workspace.blockers) or "none",
    )
    try:
        result = await provider.generate(prompt, EXTRACT_SCHEMA)
    except ProviderError as exc:
        logger.warning("Extraction failed for project {}, skipping this cycle: {}", project_id, exc)
        return []

    threshold = get_settings().dedup_similarity_threshold
    stored: list[Memory] = []
    for candidate in result.get("memories", []):
        content = (candidate.get("content") or "").strip()
        if not content or candidate.get("type") not in EXTRACT_TYPES:
            continue
        try:
            confidence = Confidence(candidate["confidence"])
        except ValueError:
            continue
        category = MemoryCategory(candidate["type"])

        embedding = embeddings.embed(content)
        existing = vector_store.query(embedding, n_results=1, where=active_where(project_id))
        if existing and existing[0][1] >= threshold:
            memories.touch(existing[0][0], confidence=confidence)
            continue

        memory = Memory(
            content=content,
            category=category,
            view=MemoryView.PROJECT,
            project_id=project_id,
            importance=_importance_for(category),
            confidence=confidence,
            source=Source(
                platform=episode.platform,
                session_id=episode.session_id,
                role="assistant",
                episode_id=episode.id,
            ),
        )
        memories.save(memory)
        vector_store.upsert(memory, embedding)
        stored.append(memory)

    if stored:
        logger.info("Extracted {} new Project Brain memories for {}", len(stored), project_id)
    return stored
