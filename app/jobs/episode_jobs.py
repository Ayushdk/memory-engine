"""Episode summarization job — summarizer model with heuristic fallback.

LLM proposes, deterministic code disposes: the summary is schema-validated
by the provider; any failure (or no provider at all) degrades to a
deterministic transcript digest, so episodes ALWAYS end up summarized.
"""

from loguru import logger

from app.engine.llm.provider import LLMProvider, ProviderError
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from app.models.domain.episode import Episode
from app.models.domain.session import ConversationMessage

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}

PROMPT_TEMPLATE = """You summarize one segment of a conversation between a \
user and an AI assistant for a memory system's internal records.

Write a summary that preserves: what was worked on, decisions made (with
their why), constraints stated, problems hit, and where the work stands.
Use ONLY information present in the conversation — do not invent details.
Skip pleasantries and smalltalk entirely. A short paragraph is enough; if
nothing of substance happened, say so in one sentence.

Conversation segment:
{transcript}
"""

# Deterministic fallback bounds: enough context to be useful, small enough
# to never bloat the workspace.
FALLBACK_TURN_CHARS = 200
FALLBACK_MAX_CHARS = 1500


def episode_turns(
    episode: Episode, working_memory: WorkingMemoryRepository
) -> list[ConversationMessage]:
    """The episode's evidence: buffered turns inside its time window.
    (episode_max_messages < working_memory_capacity, so the buffer always
    still holds the whole episode.)"""
    return [
        m
        for m in working_memory.load(episode.session_id)
        if m.timestamp >= episode.started_at
        and (episode.ended_at is None or m.timestamp <= episode.ended_at)
    ]


def transcript_of(turns: list[ConversationMessage]) -> str:
    return "\n".join(f"{m.role}: {m.content}" for m in turns)


def fallback_summary(turns: list[ConversationMessage]) -> str:
    digest = "\n".join(
        f"{m.role}: {m.content[:FALLBACK_TURN_CHARS]}" for m in turns
    )
    return digest[:FALLBACK_MAX_CHARS]


async def summarize_episode(
    episode_id: str,
    episodes: EpisodeRepository,
    working_memory: WorkingMemoryRepository,
    provider: LLMProvider | None,
) -> None:
    episode = episodes.get(episode_id)
    if episode is None or episode.status != "closed":
        return
    turns = episode_turns(episode, working_memory)
    if not turns:
        episodes.set_summary(episode_id, "")
        return

    summary = ""
    if provider is not None:
        try:
            prompt = PROMPT_TEMPLATE.format(transcript=transcript_of(turns))
            result = await provider.generate(prompt, SUMMARY_SCHEMA)
            summary = result["summary"].strip()
        except ProviderError as exc:
            logger.warning("Episode {} LLM summary failed, using fallback: {}", episode_id, exc)
    if not summary:
        summary = fallback_summary(turns)
    episodes.set_summary(episode_id, summary)
    logger.info("Episode {} summarized ({} chars)", episode_id, len(summary))


async def process_episode(
    episode_id: str,
    episodes: EpisodeRepository,
    working_memory: WorkingMemoryRepository,
    workspaces,
    summarizer: LLMProvider | None,
) -> None:
    """The full close pipeline: summarize, then fold into the project's
    workspace (episodes without a project still get summarized)."""
    from app.jobs.workspace_jobs import update_workspace

    await summarize_episode(episode_id, episodes, working_memory, summarizer)
    episode = episodes.get(episode_id)
    if episode and episode.project_id and episode.summary_internal:
        await update_workspace(episode.project_id, episode, workspaces, summarizer)
