"""Workspace update job — merges a summarized episode into the project's
working state (intelligence-layer.md §3.3).

Two summaries, two consumers, never conflated:
- internal_summary: the engine's working notes — preserves information
- transfer_summary: compact briefing for another LLM — token-budgeted

LLM proposes, deterministic code disposes: both summaries are trimmed to
their budgets after generation regardless of what the model returned, and
any provider failure degrades to a deterministic append-and-trim.
"""

from loguru import logger

from app.core.config import get_settings
from app.engine.llm.provider import LLMProvider, ProviderError
from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.models.domain.episode import Episode
from app.models.domain.workspace import Workspace
from app.services.tokenizer_service import estimate_tokens

UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "internal_summary": {"type": "string"},
        "transfer_summary": {"type": "string"},
        "goal": {"type": "string"},
        "blockers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["internal_summary", "transfer_summary", "goal", "blockers"],
}

PROMPT_TEMPLATE = """You maintain the working state of a project for an AI \
memory system.

Current working notes:
{internal}

Current goal: {goal}
Current blockers: {blockers}

A conversation episode just ended. Its summary:
{episode_summary}

Update the working state using ONLY information from the notes and the
episode. Return:
- internal_summary: concise working notes, not conversational narration —
  short factual lines covering decisions (with their why), constraints,
  current state of the work. Merge the episode in; drop what it supersedes.
- transfer_summary: a briefing for a different AI assistant picking up this
  work cold: what the project is, where the work stands, what's next. Terse
  working notes, no pleasantries. At most about {transfer_words} words.
- goal: the current objective (change only if the episode changed it; empty
  string if unknown)
- blockers: the current list (add new ones, drop resolved ones)
"""


def _trim_to_tokens(text: str, budget: int) -> str:
    if estimate_tokens(text) <= budget:
        return text
    return text[: budget * 4].rstrip()  # estimate_tokens is ceil(chars/4)


def _fallback_merge(workspace: Workspace, episode_summary: str) -> Workspace:
    """No LLM: append the episode to the notes and reuse the head as the
    transfer briefing. Loses elegance, never information."""
    settings = get_settings()
    internal = f"{workspace.internal_summary}\n- {episode_summary}".strip()
    internal = internal[-settings.workspace_internal_max_chars :]
    return workspace.model_copy(
        update={
            "internal_summary": internal,
            "transfer_summary": _trim_to_tokens(
                internal, settings.transfer_summary_token_budget
            ),
        }
    )


async def update_workspace(
    project_id: str,
    episode: Episode,
    workspaces: WorkspaceRepository,
    provider: LLMProvider | None,
) -> None:
    episode_summary = (episode.summary_internal or "").strip()
    if not episode_summary:
        return
    settings = get_settings()
    workspace = workspaces.get(project_id)

    updated: Workspace | None = None
    if provider is not None:
        prompt = PROMPT_TEMPLATE.format(
            internal=workspace.internal_summary or "(none yet)",
            goal=workspace.goal or "(unknown)",
            blockers=", ".join(workspace.blockers) or "(none)",
            episode_summary=episode_summary,
            # ~0.75 words per token is the usual rule of thumb
            transfer_words=int(settings.transfer_summary_token_budget * 0.75),
        )
        try:
            result = await provider.generate(prompt, UPDATE_SCHEMA)
            updated = workspace.model_copy(
                update={
                    "internal_summary": result["internal_summary"].strip()[
                        : settings.workspace_internal_max_chars
                    ],
                    "transfer_summary": _trim_to_tokens(
                        result["transfer_summary"].strip(),
                        settings.transfer_summary_token_budget,
                    ),
                    "goal": result["goal"].strip() or workspace.goal,
                    "blockers": [b.strip() for b in result["blockers"] if b.strip()],
                }
            )
        except ProviderError as exc:
            logger.warning("Workspace update LLM failed for {}: {}", project_id, exc)
    if updated is None:
        updated = _fallback_merge(workspace, episode_summary)

    workspaces.save(updated)
    logger.info(
        "Workspace {} updated from episode {} (transfer ~{} tokens)",
        project_id,
        episode.id,
        estimate_tokens(updated.transfer_summary),
    )
