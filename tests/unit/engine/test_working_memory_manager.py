from app.engine.working_memory.working_memory_manager import WorkingMemoryManager


def test_add_and_get_preserves_order():
    wm = WorkingMemoryManager(capacity=5)
    wm.add_message("s1", "user", "hello")
    wm.add_message("s1", "assistant", "hi")

    messages = wm.get_messages("s1")
    assert [(m.role, m.content) for m in messages] == [("user", "hello"), ("assistant", "hi")]


def test_fifo_eviction_at_capacity():
    wm = WorkingMemoryManager(capacity=3)
    for i in range(5):
        wm.add_message("s1", "user", f"msg{i}")

    assert [m.content for m in wm.get_messages("s1")] == ["msg2", "msg3", "msg4"]


def test_sessions_are_isolated():
    wm = WorkingMemoryManager(capacity=3)
    wm.add_message("s1", "user", "a")
    wm.add_message("s2", "user", "b")

    assert [m.content for m in wm.get_messages("s1")] == ["a"]
    assert [m.content for m in wm.get_messages("s2")] == ["b"]


def test_last_n_returns_most_recent():
    wm = WorkingMemoryManager(capacity=5)
    for i in range(4):
        wm.add_message("s1", "user", f"msg{i}")

    assert [m.content for m in wm.get_messages("s1", last_n=2)] == ["msg2", "msg3"]


def test_unknown_session_returns_empty():
    assert WorkingMemoryManager(capacity=3).get_messages("nope") == []


def test_clear():
    wm = WorkingMemoryManager(capacity=3)
    wm.add_message("s1", "user", "a")
    wm.clear("s1")
    assert wm.get_messages("s1") == []
    wm.clear("s1")  # clearing an unknown/empty session is a no-op


def test_capacity_defaults_to_config():
    from app.core.config import get_settings

    assert WorkingMemoryManager()._capacity == get_settings().working_memory_capacity
