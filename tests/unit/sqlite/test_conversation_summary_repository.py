"""Conversation summary repository: one row per session, replaced in place."""

from app.memory.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.models.domain.conversation_summary import ConversationSummary


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
