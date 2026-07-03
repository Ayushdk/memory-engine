"""FastAPI app factory. Transport layer only — all logic lives in app.engine."""

from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.routes import context_routes, health_routes, memory_routes
from app.core.config import get_settings
from app.core.lifecycle import lifespan
from app.core.logging import setup_logging

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    app.include_router(health_routes.router, prefix=API_PREFIX)
    app.include_router(memory_routes.router, prefix=API_PREFIX)
    app.include_router(context_routes.router, prefix=API_PREFIX)
    register_error_handlers(app)
    return app


app = create_app()
