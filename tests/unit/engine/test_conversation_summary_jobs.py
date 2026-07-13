"""Rolling conversation summary chain: LLM merge, fallback, idempotency, budget."""

import asyncio

import pytest

from app.core.config import Settings
from app.engine.llm.provider import ProviderError
from app.jobs import conversation_summary_jobs
from app.jobs.conversation_summary_jobs import SYSTEM_PROMPT, update_conversation_summary
from app.memory.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.memory.repositories.raw_message_repository import RawMessageRepository
from app.services.tokenizer_service import estimate_tokens


class FakeProvider:
    def __init__(self, summary=None, error=None):
        self._summary, self._error = summary, error
        self.prompts = []
        self.systems = []

    async def generate(self, prompt, output_schema, system=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        if self._error:
            raise ProviderError(self._error)
        return {"summary": self._summary}

    async def health(self):  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def small_budget(monkeypatch):
    monkeypatch.setattr(
        conversation_summary_jobs,
        "get_settings",
        lambda: Settings(_env_file=None, conversation_summary_token_budget=10),
    )


async def test_llm_summary_is_stored_and_messages_marked(db_conn):
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)
    raw_messages.append("s1", "user", "let's use SQLite")
    provider = FakeProvider(summary="Decided SQLite.")

    result = await update_conversation_summary("s1", raw_messages, conversation_summaries, provider)

    assert result == "Decided SQLite."
    assert conversation_summaries.get("s1").summary == "Decided SQLite."
    assert all(m.summarized for m in raw_messages.list("s1"))
    assert "let's use SQLite" in provider.prompts[0]
    assert provider.systems[0] == SYSTEM_PROMPT


async def test_chains_forward_over_previous_summary(db_conn):
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)
    raw_messages.append("s1", "user", "first message")
    provider = FakeProvider(summary="first summary")
    await update_conversation_summary("s1", raw_messages, conversation_summaries, provider)

    raw_messages.append("s1", "user", "second message")
    provider2 = FakeProvider(summary="second summary")
    await update_conversation_summary("s1", raw_messages, conversation_summaries, provider2)

    assert "first summary" in provider2.prompts[0]  # previous summary fed forward
    assert "second message" in provider2.prompts[0]
    assert "first message" not in provider2.prompts[0]  # already folded in, not re-sent
    assert conversation_summaries.get("s1").summary == "second summary"


async def test_no_unsummarized_messages_is_a_no_op(db_conn):
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)
    conversation_summaries.save(
        conversation_summaries.get("s1").model_copy(update={"summary": "existing"})
    )
    provider = FakeProvider(summary="should not be called")

    result = await update_conversation_summary("s1", raw_messages, conversation_summaries, provider)

    assert result == "existing"
    assert provider.prompts == []


async def test_provider_failure_falls_back_to_append_merge(db_conn):
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)
    raw_messages.append("s1", "user", "important decision")

    await update_conversation_summary(
        "s1", raw_messages, conversation_summaries, FakeProvider(error="down")
    )

    assert "important decision" in conversation_summaries.get("s1").summary


async def test_no_provider_uses_fallback_merge(db_conn):
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)
    raw_messages.append("s1", "user", "offline mode works")

    await update_conversation_summary("s1", raw_messages, conversation_summaries, None)

    assert "offline mode works" in conversation_summaries.get("s1").summary


async def test_concurrent_calls_for_the_same_session_never_lose_a_write(db_conn):
    """Simulates an inline Sync call racing a still-in-flight background
    episode job for the same session: both would otherwise read the same
    'unsummarized' set before either writes, and the slower one could
    overwrite the faster one's more-complete summary. The per-session lock
    must force full serialization instead."""
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)
    raw_messages.append("s1", "user", "first batch message")

    release_first = asyncio.Event()
    entered_first = asyncio.Event()

    class SlowProvider:
        def __init__(self, summary):
            self._summary = summary
            self.prompts = []

        async def generate(self, prompt, output_schema, system=None):
            self.prompts.append(prompt)
            entered_first.set()
            await release_first.wait()
            return {"summary": self._summary}

        async def health(self):  # pragma: no cover
            raise NotImplementedError

    slow = SlowProvider("summary from first call")
    first = asyncio.create_task(
        update_conversation_summary("s1", raw_messages, conversation_summaries, slow)
    )
    await entered_first.wait()  # first call is blocked mid-generate, lock held

    # A second batch arrives and a second call starts concurrently.
    raw_messages.append("s1", "user", "second batch message")
    fast = FakeProvider(summary="summary from second call")
    second = asyncio.create_task(
        update_conversation_summary("s1", raw_messages, conversation_summaries, fast)
    )
    await asyncio.sleep(0)  # let it try to acquire the lock and block

    release_first.set()
    first_result = await first
    second_result = await second

    assert first_result == "summary from first call"
    # The second call must only start after the first fully committed, so it
    # sees the first call's summary and both raw messages are folded in.
    assert "summary from first call" in fast.prompts[0]
    assert "second batch message" in fast.prompts[0]
    assert second_result == "summary from second call"
    assert conversation_summaries.get("s1").summary == "summary from second call"
    assert all(m.summarized for m in raw_messages.list("s1"))


async def test_summary_is_trimmed_to_budget(db_conn, small_budget):
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)
    raw_messages.append("s1", "user", "hello")
    provider = FakeProvider(summary="word " * 200)  # way past a 10-token budget

    await update_conversation_summary("s1", raw_messages, conversation_summaries, provider)

    assert estimate_tokens(conversation_summaries.get("s1").summary) <= 10


async def test_repeated_fallback_trimming_keeps_the_newest_content(db_conn, small_budget):
    """Under a persistently-down provider, each cycle falls back to
    append-and-trim. The trim must drop stale front content, not the just
    -arrived tail, or long-run continuity would keep losing the latest turns
    while hoarding ancient ones."""
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)

    for i in range(10):
        raw_messages.append("s1", "user", f"turn number {i}")
        await update_conversation_summary(
            "s1", raw_messages, conversation_summaries, FakeProvider(error="down")
        )

    final = conversation_summaries.get("s1").summary
    assert "turn number 9" in final  # most recent survives
    assert "turn number 0" not in final  # oldest was dropped first


async def test_summary_and_mark_are_atomic(db_conn, monkeypatch):
    """A crash (or any exception) between saving the new summary and marking
    the raw messages it consumed must roll back both, not just leave the
    second half undone — otherwise those messages would be re-fed into the
    next chain step on top of a summary that already absorbed them."""
    raw_messages = RawMessageRepository(db_conn)
    conversation_summaries = ConversationSummaryRepository(db_conn)
    raw_messages.append("s1", "user", "message before the crash")

    def boom(self, ids, commit=True):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(RawMessageRepository, "mark_summarized_by_ids", boom)

    with pytest.raises(RuntimeError):
        await update_conversation_summary(
            "s1", raw_messages, conversation_summaries, FakeProvider(summary="new summary")
        )

    # Nothing committed: summary untouched, message still unsummarized.
    assert conversation_summaries.get("s1").is_empty
    assert raw_messages.list("s1")[0].summarized is False
