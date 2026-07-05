"""Application startup/shutdown: data dirs + SQLite schema + connection."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.core.config import get_settings
from app.core.paths import ensure_data_dirs
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
    logger.info(
        "{} v{} ready on {}:{}", settings.app_name, settings.version, settings.host, settings.port
    )
    yield
    app.state.db.close()
    logger.info("Shutting down")
