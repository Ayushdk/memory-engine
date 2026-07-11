"""Episode repository: lifecycle rows, counts, inactivity queries."""

from datetime import timedelta

from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.session_repository import SessionRepository
from app.utils.time import utc_now


def make_repos(db_conn):
    return EpisodeRepository(db_conn), SessionRepository(db_conn)


def test_open_for_creates_once_and_reuses(db_conn):
    repo, _ = make_repos(db_conn)
    first = repo.open_for("s1", None, "chatgpt")
    second = repo.open_for("s1", None, "chatgpt")
    assert first.id == second.id
    assert first.status == "open"


def test_open_for_adopts_later_project_id(db_conn):
    repo, _ = make_repos(db_conn)
    repo.open_for("s1", None, "chatgpt")
    adopted = repo.open_for("s1", "proj_x", "chatgpt")
    assert adopted.project_id == "proj_x"
    assert repo.get(adopted.id).project_id == "proj_x"


def test_record_message_increments(db_conn):
    repo, _ = make_repos(db_conn)
    episode = repo.open_for("s1", None, "chatgpt")
    assert repo.record_message(episode.id) == 1
    assert repo.record_message(episode.id) == 2


def test_close_sets_reason_and_is_single_shot(db_conn):
    repo, _ = make_repos(db_conn)
    episode = repo.open_for("s1", None, "chatgpt")
    closed = repo.close(episode.id, "sync")
    assert closed.status == "closed"
    assert closed.boundary_reason == "sync"
    assert closed.ended_at is not None
    assert repo.close(episode.id, "sync") is None  # already closed
    assert repo.get_open("s1") is None


def test_set_summary_marks_summarized(db_conn):
    repo, _ = make_repos(db_conn)
    episode = repo.open_for("s1", None, "chatgpt")
    repo.close(episode.id, "sync")
    repo.set_summary(episode.id, "worked on the retrieval endpoint")
    stored = repo.get(episode.id)
    assert stored.status == "summarized"
    assert stored.summary_internal == "worked on the retrieval endpoint"


def test_list_open_inactive_uses_session_activity(db_conn):
    repo, sessions = make_repos(db_conn)
    sessions.touch("quiet", "chatgpt")
    sessions.touch("busy", "chatgpt")
    stale = repo.open_for("quiet", None, "chatgpt")
    repo.open_for("busy", None, "chatgpt")
    # Backdate the quiet session beyond any cutoff.
    db_conn.execute(
        "UPDATE sessions SET last_activity_at = ? WHERE id = 'quiet'",
        ((utc_now() - timedelta(hours=2)).isoformat(),),
    )
    inactive = repo.list_open_inactive(utc_now() - timedelta(minutes=20))
    assert [e.id for e in inactive] == [stale.id]


def test_list_filters_by_session_and_project(db_conn):
    repo, _ = make_repos(db_conn)
    a = repo.open_for("s1", "proj_a", "chatgpt")
    repo.close(a.id, "sync")
    b = repo.open_for("s1", "proj_a", "chatgpt")
    c = repo.open_for("s2", "proj_b", "claude")
    assert {e.id for e in repo.list(session_id="s1")} == {a.id, b.id}
    assert [e.id for e in repo.list(project_id="proj_b")] == [c.id]
    assert len(repo.list()) == 3
