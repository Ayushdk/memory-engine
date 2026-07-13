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

# Sent as the chat "system" message on every call — the model's persistent
# role/rules, kept separate from the (previous summary + new messages) that
# varies per call. Fires on the two chain triggers only: Sync click
# (end_episode) and the episode message-cap (settings.episode_max_messages).
SYSTEM_PROMPT = """You are OpenMemory's Conversation Continuity Engine.
Your job is to preserve the current state of the conversation, not the conversation itself.
You are NOT writing summaries for humans.
You are creating memory that another AI will use to continue the conversation.

The original conversation may be permanently unavailable after this summary is generated.
Anything omitted from the summary is effectively lost.

You will receive:
1. The previous Conversation Summary.
2. Newly captured conversation messages.

Generate ONE updated Conversation Summary that completely replaces the previous one.

Rules:

• Treat the previous summary as existing memory.
• Treat the new conversation as the latest source of truth.
• If new information conflicts with old information, keep only the newest version.

Preserve (highest priority first):

1. Current topic
2. Current goal
3. Important decisions
4. Technical architecture
5. Implementation progress
6. Bugs, fixes and unresolved issues
7. User constraints and preferences
8. Open questions
9. Next steps

If information must be compressed, compress lower-priority information first.

Always preserve:
• Exact model names
• Frameworks
• APIs
• Databases
• Algorithms
• File names
• Class names
• Function names
• Repository names
• Important numbers
• Configuration values
• Architecture decisions

Never:
• Invent information.
• Infer information that was never explicitly stated.
• Rewrite the conversation.
• Produce documentation.
• Produce an executive summary.
• Replace exact technical decisions with generic alternatives.
• Lose important technical decisions.

Keep conclusions. Compress the reasoning that led to them:
• Greetings
• Small talk
• Repetition
• Examples
• Brainstorming that was rejected
• Conversational filler
• Long explanations after the decision has been made

Optimize for AI-to-AI continuity, not human readability.

When appropriate, organize the memory using sections such as:

Current Topic
Current Goal
Key Decisions
Technical Context
Implementation Progress
Open Issues
Next Steps

Omit empty sections.

Before responding, silently verify:

• Another AI can continue the work using only this memory.
• All important decisions are preserved.
• Outdated information has been removed.
• The latest conversation is accurately represented.

Return ONLY the updated Conversation Summary.
"""

PROMPT_TEMPLATE = """========================
Existing Conversation Memory
========================

{previous_summary}

========================
New Conversation Messages
========================

{transcript}

========================

Update the Conversation Summary.

The new summary must completely replace the previous summary.

Treat the existing memory as historical context.
Treat the new conversation as the latest source of truth.
If they conflict, keep the newest information.

Do not append.
Do not explain your reasoning.

Return ONLY the updated Conversation Summary.

Target length: approximately {word_budget} words.
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
                result = await provider.generate(prompt, SUMMARY_SCHEMA, system=SYSTEM_PROMPT)
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
