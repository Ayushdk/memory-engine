"""Raw message ledger: append-only, never deleted, id-based marking."""

from app.memory.repositories.raw_message_repository import RawMessageRepository


def test_append_and_list_round_trip(db_conn):
    repo = RawMessageRepository(db_conn)
    repo.append("s1", "user", "hello", project_id="proj_x", platform="chatgpt")
    repo.append("s1", "assistant", "hi there")

    stored = repo.list("s1")
    assert [(m.role, m.content) for m in stored] == [("user", "hello"), ("assistant", "hi there")]
    assert stored[0].project_id == "proj_x"
    assert stored[0].platform == "chatgpt"
    assert all(not m.summarized for m in stored)


def test_unsummarized_excludes_flagged_messages(db_conn):
    repo = RawMessageRepository(db_conn)
    keep = repo.append("s1", "user", "not yet folded in")
    flagged = repo.append("s1", "user", "already folded in")
    repo.mark_summarized_by_ids([flagged.id])

    unsummarized = repo.unsummarized("s1")
    assert [m.id for m in unsummarized] == [keep.id]


def test_mark_summarized_by_ids_never_deletes_rows(db_conn):
    repo = RawMessageRepository(db_conn)
    message = repo.append("s1", "user", "keep me forever")
    repo.mark_summarized_by_ids([message.id])

    assert len(repo.list("s1")) == 1
    assert repo.list("s1")[0].summarized is True


def test_mark_summarized_by_ids_only_flags_the_given_ids(db_conn):
    repo = RawMessageRepository(db_conn)
    a = repo.append("s1", "user", "flag me")
    b = repo.append("s1", "user", "leave me alone")
    repo.mark_summarized_by_ids([a.id])

    by_id = {m.id: m.summarized for m in repo.list("s1")}
    assert by_id[a.id] is True
    assert by_id[b.id] is False


def test_mark_summarized_by_ids_empty_list_is_a_no_op(db_conn):
    repo = RawMessageRepository(db_conn)
    repo.append("s1", "user", "untouched")
    repo.mark_summarized_by_ids([])

    assert repo.list("s1")[0].summarized is False
