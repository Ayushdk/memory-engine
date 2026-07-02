"""Application startup/shutdown. Phase 1 adds SQLite + Chroma initialization here."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.core.config import get_settings
from app.core.paths import ensure_data_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_data_dirs()
    logger.info(
        "{} v{} ready on {}:{}", settings.app_name, settings.version, settings.host, settings.port
    )
    yield
    logger.info("Shutting down")
