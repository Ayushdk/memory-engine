"""Rolling Current Context Summary — the conversation compression chain.

Every time it runs:
    New Summary = Summarize(Previous Summary + All Unsummarized Raw Messages)
The previous summary is replaced; those raw messages are marked summarized.
This is the canonical conversation state for cross-AI Sync — independent of
episode boundaries and never conflated with workspace/project knowledge.

LLM proposes, deterministic code disposes: any provider failure degrades to
a deterministic append-and-trim, so the chain never stalls.
"""

import asyncio
from collections import defaultdict

from loguru import logger

from app.core.config import get_settings
from app.engine.llm.provider import LLMProvider, ProviderError
from app.memory.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.memory.repositories.raw_message_repository import RawMessageRepository
from app.models.domain.conversation_summary import ConversationSummary
from app.models.domain.raw_message import RawMessage
from app.services.tokenizer_service import estimate_tokens

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}

PROMPT_TEMPLATE = """You maintain a single rolling summary of an ongoing \
conversation between a user and an AI assistant, so the conversation can be \
handed to a different AI assistant with full context.

Previous summary of the conversation so far:
{previous_summary}

New messages since that summary:
{transcript}

Write the new, complete summary: integrate what still matters from the \
previous summary with what just happened — do not simply append. Preserve \
decisions (with their why), constraints, open threads, and where things \
stand. Use ONLY information present above. Skip pleasantries. At most about \
{word_budget} words.
"""

FALLBACK_TURN_CHARS = 200

# ponytail: the inline Sync call and a still-queued background episode job
# can both chain the same session's summary concurrently; a per-session lock
# serializes their read-modify-write so neither overwrites the other's work.
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def transcript_of(messages: list[RawMessage]) -> str:
    return "\n".join(f"{m.role}: {m.content}" for m in messages)


def _trim_to_tokens(text: str, budget: int) -> str:
    """Bounds growth by keeping the most RECENT content — the tail, not the
    head — so a rolling summary that hits this repeatedly (e.g. the provider
    is down for a while and every step falls back to append-and-trim) loses
    stale context first, never the latest turns."""
    if estimate_tokens(text) <= budget:
        return text
    return text[-budget * 4 :].lstrip()  # estimate_tokens is ceil(chars/4)


def _fallback_merge(previous_summary: str, messages: list[RawMessage]) -> str:
    digest = "\n".join(f"{m.role}: {m.content[:FALLBACK_TURN_CHARS]}" for m in messages)
    return f"{previous_summary}\n{digest}".strip() if previous_summary else digest


async def update_conversation_summary(
    session_id: str,
    raw_messages: RawMessageRepository,
    conversation_summaries: ConversationSummaryRepository,
    provider: LLMProvider | None,
) -> str:
    """Chains the session's rolling summary forward over whatever hasn't
    been folded in yet. A no-op (returns the unchanged summary) when there's
    nothing new — naturally idempotent, safe to call from more than one
    trigger (an inline Sync and the background episode-close job) without
    double-applying messages. The read-modify-write is serialized per
    session so an inline Sync racing a still-queued background job can never
    overwrite the other's freshly-chained summary."""
    async with _locks[session_id]:
        unsummarized = raw_messages.unsummarized(session_id)
        previous = conversation_summaries.get(session_id).summary
        if not unsummarized:
            return previous

        settings = get_settings()
        summary = ""
        if provider is not None:
            try:
                transcript = transcript_of(unsummarized)
                prompt = PROMPT_TEMPLATE.format(
                    previous_summary=previous or "(none yet — this is the first summary)",
                    transcript=transcript,
                    # ~0.75 words per token is the usual rule of thumb
                    word_budget=int(settings.conversation_summary_token_budget * 0.75),
                )
                logger.debug(
                    "conversation_summary input session={} messages={} transcript_chars={} "
                    "prompt_chars={}",
                    session_id, len(unsummarized), len(transcript), len(prompt),
                )
                result = await provider.generate(prompt, SUMMARY_SCHEMA)
                summary = result["summary"].strip()
            except ProviderError as exc:
                logger.warning(
                    "Conversation summary LLM failed for session {}, using fallback: {}",
                    session_id, exc,
                )
        if not summary:
            summary = _fallback_merge(previous, unsummarized)
        summary = _trim_to_tokens(summary, settings.conversation_summary_token_budget)

        # Single transaction: a crash between these two writes must never
        # leave the summary saved while its source messages are still
        # "unsummarized" (that would re-feed them into the next chain step
        # on top of a summary that already absorbed them — duplication).
        with raw_messages.conn:
            conversation_summaries.save(
                ConversationSummary(session_id=session_id, summary=summary), commit=False
            )
            raw_messages.mark_summarized_by_ids([m.id for m in unsummarized], commit=False)
        logger.info(
            "Conversation summary for session {} updated ({} messages folded in, {} chars)",
            session_id, len(unsummarized), len(summary),
        )
        return summary
