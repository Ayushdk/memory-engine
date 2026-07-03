"""Application startup/shutdown: data dirs + SQLite schema + connection."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.core.config import get_settings
from app.core.paths import ensure_data_dirs
from app.memory.sqlite.connection import create_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_data_dirs()
    app.state.db = create_connection()
    logger.info(
        "{} v{} ready on {}:{}", settings.app_name, settings.version, settings.host, settings.port
    )
    yield
    app.state.db.close()
    logger.info("Shutting down")
