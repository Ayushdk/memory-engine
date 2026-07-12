"""Workspace update job: LLM merge, budget enforcement, fallback merge."""

import pytest

from app.core.config import Settings
from app.engine.llm.provider import ProviderError
from app.jobs import workspace_jobs
from app.jobs.workspace_jobs import update_workspace
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.models.domain.workspace import Workspace
from app.services.tokenizer_service import estimate_tokens


class FakeProvider:
    def __init__(self, result=None, error=None):
        self._result, self._error = result, error
        self.prompts = []

    async def generate(self, prompt, output_schema):
        self.prompts.append(prompt)
        if self._error:
            raise ProviderError(self._error)
        return self._result

    async def health(self):  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def small_budget(monkeypatch):
    monkeypatch.setattr(
        workspace_jobs,
        "get_settings",
        lambda: Settings(
            _env_file=None, transfer_summary_token_budget=10, workspace_internal_max_chars=200
        ),
    )


def summarized_episode(db_conn, summary="Decided React+Vite for the dashboard."):
    episodes = EpisodeRepository(db_conn)
    episode = episodes.open_for("s1", "proj_x", "chatgpt")
    episodes.close(episode.id, "sync")
    episodes.set_summary(episode.id, summary)
    return episodes.get(episode.id)


async def test_llm_result_is_stored(db_conn, small_budget):
    workspaces = WorkspaceRepository(db_conn)
    provider = FakeProvider(
        result={
            "internal_summary": "- dashboard: React+Vite decided",
            "transfer_summary": "React+Vite dashboard.",
            "goal": "ship dashboard",
            "blockers": ["  ", "vite config"],
        }
    )
    await update_workspace("proj_x", summarized_episode(db_conn), workspaces, provider)
    workspace = workspaces.get("proj_x")
    assert workspace.internal_summary == "- dashboard: React+Vite decided"
    assert workspace.transfer_summary == "React+Vite dashboard."
    assert workspace.goal == "ship dashboard"
    assert workspace.blockers == ["vite config"]  # empties dropped
    assert "Decided React+Vite" in provider.prompts[0]  # episode reached the model


async def test_transfer_summary_is_trimmed_to_budget(db_conn, small_budget):
    workspaces = WorkspaceRepository(db_conn)
    provider = FakeProvider(
        result={
            "internal_summary": "x",
            "transfer_summary": "word " * 200,  # way past 10 tokens
            "goal": "",
            "blockers": [],
        }
    )
    await update_workspace("proj_x", summarized_episode(db_conn), workspaces, provider)
    assert estimate_tokens(workspaces.get("proj_x").transfer_summary) <= 10


async def test_empty_goal_keeps_the_existing_goal(db_conn, small_budget):
    workspaces = WorkspaceRepository(db_conn)
    workspaces.save(Workspace(project_id="proj_x", goal="original goal"))
    provider = FakeProvider(
        result={"internal_summary": "x", "transfer_summary": "y", "goal": "", "blockers": []}
    )
    await update_workspace("proj_x", summarized_episode(db_conn), workspaces, provider)
    assert workspaces.get("proj_x").goal == "original goal"


async def test_provider_failure_falls_back_to_append_merge(db_conn, small_budget):
    workspaces = WorkspaceRepository(db_conn)
    workspaces.save(Workspace(project_id="proj_x", internal_summary="- existing note"))
    await update_workspace(
        "proj_x", summarized_episode(db_conn), workspaces, FakeProvider(error="down")
    )
    workspace = workspaces.get("proj_x")
    assert "existing note" in workspace.internal_summary
    assert "Decided React+Vite" in workspace.internal_summary
    assert estimate_tokens(workspace.transfer_summary) <= 10


async def test_no_provider_uses_fallback_and_episode_without_summary_is_skipped(
    db_conn, small_budget
):
    workspaces = WorkspaceRepository(db_conn)
    await update_workspace("proj_x", summarized_episode(db_conn), workspaces, None)
    assert "Decided React+Vite" in workspaces.get("proj_x").internal_summary

    empty = summarized_episode(db_conn, summary="")
    before = workspaces.get("proj_x")
    await update_workspace("proj_x", empty, workspaces, None)
    assert workspaces.get("proj_x").internal_summary == before.internal_summary
