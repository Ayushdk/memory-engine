"""Episode boundary policy: message cap, explicit sync, inactivity sweep."""

from datetime import timedelta

import pytest

from app.core.config import Settings
from app.engine.episodes import tracker as tracker_module
from app.engine.episodes.tracker import EpisodeTracker
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.session_repository import SessionRepository
from app.utils.time import utc_now


@pytest.fixture(autouse=True)
def small_cap(monkeypatch):
    monkeypatch.setattr(
        tracker_module,
        "get_settings",
        lambda: Settings(_env_file=None, episode_max_messages=3, episode_inactivity_minutes=20),
    )


@pytest.fixture
def setup(db_conn):
    closed = []
    repo = EpisodeRepository(db_conn)
    tracker = EpisodeTracker(repo, on_close=closed.append)
    return tracker, repo, SessionRepository(db_conn), closed


def test_messages_accumulate_in_one_open_episode(setup):
    tracker, repo, _, closed = setup
    first = tracker.on_message("s1", "proj_a", "chatgpt")
    second = tracker.on_message("s1", "proj_a", "chatgpt")
    assert first.id == second.id
    assert closed == []
    assert repo.get(first.id).message_count == 2


def test_message_cap_closes_and_next_message_starts_fresh(setup):
    tracker, repo, _, closed = setup
    for _ in range(3):
        episode = tracker.on_message("s1", None, "chatgpt")
    assert [e.id for e in closed] == [episode.id]
    assert closed[0].boundary_reason == "message-cap"
    assert closed[0].message_count == 3
    fresh = tracker.on_message("s1", None, "chatgpt")
    assert fresh.id != episode.id


def test_end_episode_on_sync(setup):
    tracker, repo, _, closed = setup
    episode = tracker.on_message("s1", None, "chatgpt")
    ended = tracker.end_episode("s1", "sync")
    assert ended.id == episode.id
    assert ended.boundary_reason == "sync"
    assert closed == [ended]
    assert tracker.end_episode("s1", "sync") is None  # nothing open now


def test_sweep_closes_only_inactive_sessions(setup):
    tracker, repo, sessions, closed = setup
    sessions.touch("quiet", "chatgpt")
    sessions.touch("busy", "chatgpt")
    stale = tracker.on_message("quiet", None, "chatgpt")
    tracker.on_message("busy", None, "chatgpt")
    repo._conn.execute(
        "UPDATE sessions SET last_activity_at = ? WHERE id = 'quiet'",
        ((utc_now() - timedelta(hours=1)).isoformat(),),
    )
    swept = tracker.sweep()
    assert [e.id for e in swept] == [stale.id]
    assert swept[0].boundary_reason == "inactivity"
    assert repo.get_open("busy") is not None
