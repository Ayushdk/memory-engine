"""Application startup/shutdown: data dirs + SQLite schema + connection."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.core.config import get_settings
from app.core.paths import ensure_data_dirs
from app.engine.episodes.tracker import EpisodeTracker
from app.engine.llm.model_manager import ensure_models
from app.engine.llm.provider import create_provider
from app.jobs.episode_jobs import process_episode
from app.jobs.job_runner import JobRunner
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.memory.sqlite.connection import create_connection
from app.services.embedding_service import get_embedding_service


def _warm_embedding_model() -> None:
    """MiniLM loads lazily on first embed (~10s cold); warming it here makes
    the extension's first ingest instantaneous instead of a timeout risk."""
    try:
        get_embedding_service().embed("warmup")
        logger.info("Embedding model warmed up")
    except Exception as exc:  # startup must never die over a warmup
        logger.warning("Embedding warmup failed (first ingest will be slow): {}", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_data_dirs()
    app.state.db = create_connection()
    # Background thread: /health responds immediately while the model loads.
    asyncio.get_running_loop().run_in_executor(None, _warm_embedding_model)
    # Fire-and-forget: pull any missing Ollama models; /health shows progress.
    app.state.model_pull_task = asyncio.create_task(ensure_models(settings))

    # Episodes: boundary tracking + async summarization (intelligence-layer §4).
    episodes = EpisodeRepository(app.state.db)
    working_memory_repo = WorkingMemoryRepository(app.state.db)
    workspaces = WorkspaceRepository(app.state.db)
    app.state.workspace_repository = workspaces
    runner = JobRunner()
    app.state.job_runner = runner
    app.state.episode_tracker = EpisodeTracker(
        episodes,
        on_close=lambda episode: runner.enqueue(
            f"process-episode:{episode.id}",
            lambda: process_episode(
                episode.id,
                episodes,
                working_memory_repo,
                workspaces,
                create_provider("summarizer"),
            ),
        ),
    )
    runner.start()
    runner.start_periodic(
        "episode-sweep",
        settings.episode_sweep_seconds,
        # sweep is sync + fast; wrap for the runner's coroutine contract
        lambda: asyncio.to_thread(app.state.episode_tracker.sweep),
    )
    logger.info(
        "{} v{} ready on {}:{}", settings.app_name, settings.version, settings.host, settings.port
    )
    yield
    await runner.stop()
    app.state.model_pull_task.cancel()
    app.state.db.close()
    logger.info("Shutting down")
