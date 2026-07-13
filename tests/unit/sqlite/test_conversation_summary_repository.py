"""Conversation summary repository: one row per session, replaced in place."""

from datetime import timedelta

from app.memory.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.models.domain.conversation_summary import ConversationSummary
from app.utils.time import utc_now


def test_missing_summary_is_a_pristine_default(db_conn):
    summary = ConversationSummaryRepository(db_conn).get("s1")
    assert summary.session_id == "s1"
    assert summary.is_empty


def test_save_and_get_round_trip(db_conn):
    repo = ConversationSummaryRepository(db_conn)
    repo.save(ConversationSummary(session_id="s1", summary="decided SQLite"))
    loaded = repo.get("s1")
    assert loaded.summary == "decided SQLite"
    assert not loaded.is_empty


def test_save_replaces_the_previous_summary(db_conn):
    repo = ConversationSummaryRepository(db_conn)
    repo.save(ConversationSummary(session_id="s1", summary="first"))
    repo.save(ConversationSummary(session_id="s1", summary="second"))
    assert repo.get("s1").summary == "second"


def test_latest_other_finds_the_most_recent_different_session(db_conn):
    """Cross-AI handoff: a brand-new chat's own summary is empty, so Sync
    there should find whatever the user was just doing on another chat."""
    repo = ConversationSummaryRepository(db_conn)
    repo.save(ConversationSummary(session_id="chatgpt-a", summary="decided SQLite"))

    found = repo.latest_other("claude-b", since=utc_now() - timedelta(minutes=30))

    assert found is not None
    assert found.session_id == "chatgpt-a"
    assert found.summary == "decided SQLite"


def test_latest_other_excludes_the_requesting_session(db_conn):
    repo = ConversationSummaryRepository(db_conn)
    repo.save(ConversationSummary(session_id="s1", summary="own summary"))

    assert repo.latest_other("s1", since=utc_now() - timedelta(minutes=30)) is None


def test_latest_other_excludes_empty_summaries(db_conn):
    repo = ConversationSummaryRepository(db_conn)
    repo.get("chatgpt-a")  # never saved: no row, or a row with summary=""
    repo.save(ConversationSummary(session_id="chatgpt-a", summary=""))

    assert repo.latest_other("claude-b", since=utc_now() - timedelta(minutes=30)) is None


def test_latest_other_excludes_stale_summaries(db_conn):
    repo = ConversationSummaryRepository(db_conn)
    repo.save(ConversationSummary(session_id="chatgpt-a", summary="old context"))

    found = repo.latest_other("claude-b", since=utc_now() + timedelta(minutes=1))

    assert found is None


def test_latest_other_prefers_the_most_recently_updated_session(db_conn):
    repo = ConversationSummaryRepository(db_conn)
    repo.save(ConversationSummary(session_id="chatgpt-a", summary="older"))
    repo.save(ConversationSummary(session_id="chatgpt-b", summary="newer"))

    found = repo.latest_other("claude-c", since=utc_now() - timedelta(minutes=30))

    assert found.summary == "newer"
