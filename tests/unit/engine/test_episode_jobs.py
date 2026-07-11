"""Episode summarization job: LLM path, fallback path, evidence window."""

from datetime import timedelta

import pytest

from app.engine.llm.provider import ProviderError
from app.jobs.episode_jobs import summarize_episode
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from app.models.domain.session import ConversationMessage
from app.utils.time import utc_now


class FakeProvider:
    def __init__(self, summary=None, error=None):
        self._summary, self._error = summary, error
        self.prompts = []

    async def generate(self, prompt, output_schema):
        self.prompts.append(prompt)
        if self._error:
            raise ProviderError(self._error)
        return {"summary": self._summary}

    async def health(self):  # pragma: no cover - Protocol completeness
        raise NotImplementedError


@pytest.fixture
def repos(db_conn):
    return EpisodeRepository(db_conn), WorkingMemoryRepository(db_conn)


def closed_episode_with_turns(repos, turns):
    episodes, working_memory = repos
    # Mirror production: the episode's window starts at its first message.
    episode = episodes.open_for(
        "s1", "proj_a", "chatgpt", started_at=min(t.timestamp for t in turns)
    )
    working_memory.save_snapshot("s1", turns)
    return episodes.close(episode.id, "sync")


def turn(role, content, **kwargs):
    return ConversationMessage(role=role, content=content, **kwargs)


async def test_llm_summary_is_stored(repos):
    episodes, working_memory = repos
    episode = closed_episode_with_turns(
        repos, [turn("user", "let's use SQLite"), turn("assistant", "agreed, single file")]
    )
    provider = FakeProvider(summary="Chose SQLite for storage.")
    await summarize_episode(episode.id, episodes, working_memory, provider)
    stored = episodes.get(episode.id)
    assert stored.status == "summarized"
    assert stored.summary_internal == "Chose SQLite for storage."
    assert "let's use SQLite" in provider.prompts[0]  # transcript reached the model


async def test_provider_failure_falls_back_to_digest(repos):
    episodes, working_memory = repos
    episode = closed_episode_with_turns(repos, [turn("user", "important decision here")])
    await summarize_episode(
        episode.id, episodes, working_memory, FakeProvider(error="model exploded")
    )
    stored = episodes.get(episode.id)
    assert stored.status == "summarized"
    assert "important decision here" in stored.summary_internal


async def test_no_provider_uses_digest(repos):
    episodes, working_memory = repos
    episode = closed_episode_with_turns(repos, [turn("user", "offline mode works")])
    await summarize_episode(episode.id, episodes, working_memory, None)
    assert "offline mode works" in episodes.get(episode.id).summary_internal


async def test_only_turns_inside_the_episode_window_count(repos):
    episodes, working_memory = repos
    stale = turn("user", "from a previous episode", timestamp=utc_now() - timedelta(hours=3))
    fresh = turn("user", "current work")
    # This episode began at the fresh turn; the stale one belongs to a
    # previous episode still sitting in the buffer.
    episode = episodes.open_for("s1", "proj_a", "chatgpt", started_at=fresh.timestamp)
    working_memory.save_snapshot("s1", [stale, fresh])
    episode = episodes.close(episode.id, "sync")
    provider = FakeProvider(summary="ok")
    await summarize_episode(episode.id, episodes, working_memory, provider)
    assert "from a previous episode" not in provider.prompts[0]
    assert "current work" in provider.prompts[0]


async def test_empty_episode_summarizes_to_empty(repos):
    episodes, working_memory = repos
    episode = episodes.open_for("empty", None, "chatgpt")
    episodes.close(episode.id, "inactivity")
    await summarize_episode(episode.id, episodes, working_memory, FakeProvider(summary="x"))
    stored = episodes.get(episode.id)
    assert stored.status == "summarized"
    assert stored.summary_internal == ""


async def test_open_or_missing_episode_is_ignored(repos):
    episodes, working_memory = repos
    open_episode = episodes.open_for("s9", None, "chatgpt")
    await summarize_episode(open_episode.id, episodes, working_memory, None)
    assert episodes.get(open_episode.id).status == "open"  # untouched
    await summarize_episode("ep_missing", episodes, working_memory, None)  # no raise
