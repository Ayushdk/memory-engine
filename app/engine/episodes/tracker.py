"""Episode boundary policy (intelligence-layer.md §4) — deterministic.

Boundaries: message cap (checked on every ingested message), Sync click
(`end_episode`), and inactivity (`sweep`, driven by a periodic job).
Tab close needs no signal of its own: a closed tab stops producing messages,
so the inactivity sweep closes its episode. Conversation switches map to new
session ids, which simply open their own episodes.

On every close the tracker hands the episode to `on_close` (the job runner
enqueues summarization) — the tracker itself never summarizes.
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from loguru import logger

from app.core.config import get_settings
from app.memory.repositories.episode_repository import EpisodeRepository
from app.models.domain.episode import Episode
from app.utils.time import utc_now


class EpisodeTracker:
    def __init__(
        self,
        episodes: EpisodeRepository,
        on_close: Callable[[Episode], None],
    ) -> None:
        self._episodes = episodes
        self._on_close = on_close

    def on_message(
        self,
        session_id: str,
        project_id: str | None,
        platform: str | None,
        at: datetime | None = None,
    ) -> Episode:
        """Called once per ingested message (`at` = the message's timestamp,
        which anchors a new episode's evidence window). Opens an episode if
        needed; closes it at the message cap (the next message starts fresh)."""
        episode = self._episodes.open_for(session_id, project_id, platform, started_at=at)
        count = self._episodes.record_message(episode.id)
        if count >= get_settings().episode_max_messages:
            self._close(episode.id, "message-cap")
        return episode

    def end_episode(self, session_id: str, reason: str = "sync") -> Episode | None:
        """Explicit boundary (Sync click). No open episode → None, not an error."""
        episode = self._episodes.get_open(session_id)
        return self._close(episode.id, reason) if episode else None

    def sweep(self) -> list[Episode]:
        """Close every open episode whose session has gone quiet."""
        cutoff = utc_now() - timedelta(minutes=get_settings().episode_inactivity_minutes)
        return [
            closed
            for episode in self._episodes.list_open_inactive(cutoff)
            if (closed := self._close(episode.id, "inactivity"))
        ]

    def _close(self, episode_id: str, reason: str) -> Episode | None:
        closed = self._episodes.close(episode_id, reason)
        if closed:
            logger.info("Episode {} closed ({}, {} messages)", closed.id, reason, closed.message_count)
            self._on_close(closed)
        return closed
