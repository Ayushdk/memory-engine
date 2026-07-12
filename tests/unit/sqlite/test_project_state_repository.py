"""ProjectStateRepository: append-only versioning, never overwritten."""

from app.memory.repositories.project_state_repository import ProjectStateRepository


def test_save_auto_increments_version(db_conn):
    repo = ProjectStateRepository(db_conn)

    first = repo.save("proj_x", "v1 content", generated_from=["mem_a"])
    second = repo.save("proj_x", "v2 content", generated_from=["mem_a", "mem_b"])

    assert first.version == 1
    assert second.version == 2
    assert repo.latest("proj_x").content == "v2 content"


def test_versions_are_project_scoped(db_conn):
    repo = ProjectStateRepository(db_conn)

    repo.save("proj_x", "x content", generated_from=[])
    repo.save("proj_y", "y content", generated_from=[])

    assert repo.latest("proj_x").content == "x content"
    assert repo.latest("proj_y").content == "y content"


def test_list_versions_ordered_newest_first(db_conn):
    repo = ProjectStateRepository(db_conn)
    repo.save("proj_x", "v1", generated_from=[])
    repo.save("proj_x", "v2", generated_from=[])
    repo.save("proj_x", "v3", generated_from=[])

    versions = repo.list_versions("proj_x")

    assert [v.version for v in versions] == [3, 2, 1]


def test_latest_returns_none_when_no_state(db_conn):
    repo = ProjectStateRepository(db_conn)
    assert repo.latest("proj_unknown") is None
