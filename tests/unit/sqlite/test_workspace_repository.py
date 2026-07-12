"""Workspace repository: state row, reset, archive snapshots."""

from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.models.domain.workspace import Workspace


def test_missing_workspace_is_a_pristine_default(db_conn):
    workspace = WorkspaceRepository(db_conn).get("proj_x")
    assert workspace.project_id == "proj_x"
    assert workspace.is_empty


def test_save_and_get_round_trip(db_conn):
    repo = WorkspaceRepository(db_conn)
    repo.save(
        Workspace(
            project_id="proj_x",
            internal_summary="notes",
            transfer_summary="briefing",
            goal="ship phase 2",
            blockers=["ollama flaky"],
        )
    )
    loaded = repo.get("proj_x")
    assert loaded.internal_summary == "notes"
    assert loaded.transfer_summary == "briefing"
    assert loaded.goal == "ship phase 2"
    assert loaded.blockers == ["ollama flaky"]
    assert not loaded.is_empty


def test_reset_clears_the_state(db_conn):
    repo = WorkspaceRepository(db_conn)
    repo.save(Workspace(project_id="proj_x", internal_summary="notes"))
    repo.reset("proj_x")
    assert repo.get("proj_x").is_empty


def test_archive_snapshots_then_resets(db_conn):
    repo = WorkspaceRepository(db_conn)
    repo.save(Workspace(project_id="proj_x", internal_summary="notes", goal="g"))
    archive_id = repo.archive("proj_x")
    assert archive_id.startswith("wsa_")
    assert repo.get("proj_x").is_empty
    archives = repo.list_archives("proj_x")
    assert len(archives) == 1
    assert archives[0].internal_summary == "notes"
    assert archives[0].goal == "g"


def test_archiving_an_empty_workspace_is_a_noop(db_conn):
    repo = WorkspaceRepository(db_conn)
    assert repo.archive("proj_never_used") is None
    assert repo.list_archives("proj_never_used") == []
