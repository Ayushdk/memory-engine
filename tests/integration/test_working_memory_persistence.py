"""Working memory persistence + session tracking (M1 Step 5)."""

from datetime import timedelta

import pytest

from app.engine.working_memory.persistence import PersistentWorkingMemory
from app.engine.working_memory.working_memory_manager import WorkingMemoryManager
from app.memory.repositories.session_repository import SessionRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from app.utils.time import utc_now


@pytest.fixture
def repos(db_conn):
    return WorkingMemoryRepository(db_conn), SessionRepository(db_conn)


def make_wm(repos, capacity=5):
    """A fresh PersistentWorkingMemory over the same DB — 'an engine (re)start'."""
    wm_repo, session_repo = repos
    return PersistentWorkingMemory(WorkingMemoryManager(capacity), wm_repo, session_repo)


def contents(wm, session_id):
    return [m.content for m in wm.get_messages(session_id)]


def test_session_created_on_first_message(repos):
    wm = make_wm(repos)
    wm.add_message("s1", "user", "hello", platform="chatgpt", project_id="proj_x")

    session = repos[1].get("s1")
    assert session.platform == "chatgpt"
    assert session.project_id == "proj_x"
    assert session.started_at is not None
    assert session.last_activity_at >= session.started_at


def test_snapshot_persisted_per_message(repos):
    wm = make_wm(repos)
    wm.add_message("s1", "user", "one")
    wm.add_message("s1", "assistant", "two")

    stored = repos[0].load("s1")
    assert [(m.role, m.content) for m in stored] == [("user", "one"), ("assistant", "two")]
    assert all(m.timestamp for m in stored)


def test_restore_after_restart(repos):
    first = make_wm(repos)
    first.add_message("s1", "user", "before restart")
    first.add_message("s1", "assistant", "still here")

    rebooted = make_wm(repos)  # brand-new manager, same DB
    assert contents(rebooted, "s1") == ["before restart", "still here"]


def test_multiple_sessions_survive_restart(repos):
    first = make_wm(repos)
    first.add_message("s1", "user", "a", platform="chatgpt")
    first.add_message("s2", "user", "b", platform="claude")

    rebooted = make_wm(repos)
    assert contents(rebooted, "s1") == ["a"]
    assert contents(rebooted, "s2") == ["b"]


def test_active_session_lookup(repos):
    wm = make_wm(repos)
    wm.add_message("recent", "user", "hi", platform="claude")

    _, session_repo = repos
    active = session_repo.list_active(since=utc_now() - timedelta(minutes=60))
    assert [s.id for s in active] == ["recent"]
    assert session_repo.list_active(since=utc_now() + timedelta(seconds=1)) == []


def test_active_sessions_most_recent_first(repos):
    wm = make_wm(repos)
    wm.add_message("older", "user", "1", platform="chatgpt")
    wm.add_message("newer", "user", "2", platform="claude")

    active = repos[1].list_active(since=utc_now() - timedelta(minutes=60))
    assert [s.id for s in active] == ["newer", "older"]


def test_fifo_still_applies_and_is_persisted(repos):
    wm = make_wm(repos, capacity=3)
    for i in range(5):
        wm.add_message("s1", "user", f"msg{i}")

    assert contents(wm, "s1") == ["msg2", "msg3", "msg4"]
    rebooted = make_wm(repos, capacity=3)
    assert contents(rebooted, "s1") == ["msg2", "msg3", "msg4"]


def test_restore_respects_smaller_capacity(repos):
    big = make_wm(repos, capacity=10)
    for i in range(6):
        big.add_message("s1", "user", f"msg{i}")

    small = make_wm(repos, capacity=3)  # restart with a reduced capacity setting
    assert contents(small, "s1") == ["msg3", "msg4", "msg5"]  # newest kept


def test_clear_removes_snapshot_too(repos):
    wm = make_wm(repos)
    wm.add_message("s1", "user", "gone soon")
    wm.clear("s1")

    assert contents(wm, "s1") == []
    assert make_wm(repos).get_messages("s1") == []  # restart confirms deletion


def test_title_is_sticky_like_project(repos):
    wm = make_wm(repos)
    wm.add_message("s1", "user", "a", platform="chatgpt", title="Designing OpenMemory")
    wm.add_message("s1", "user", "b", platform="chatgpt")  # no title passed

    session = repos[1].get("s1")
    assert session.title == "Designing OpenMemory"


def test_project_id_upgrade_but_never_downgrade(repos):
    wm = make_wm(repos)
    wm.add_message("s1", "user", "no project yet", platform="chatgpt")
    assert repos[1].get("s1").project_id is None

    wm.add_message("s1", "user", "picked one", platform="chatgpt", project_id="proj_x")
    assert repos[1].get("s1").project_id == "proj_x"

    wm.add_message("s1", "user", "another message", platform="chatgpt")  # no project passed
    assert repos[1].get("s1").project_id == "proj_x"  # sticky
