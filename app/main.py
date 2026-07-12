"""FastAPI app factory. Transport layer only — all logic lives in app.engine."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.error_handlers import register_error_handlers
from app.api.routes import (
    context_routes,
    episode_routes,
    health_routes,
    memory_routes,
    project_routes,
    project_state_routes,
    workspace_routes,
)
from app.api.security import require_token
from app.core.config import get_settings
from app.core.lifecycle import lifespan
from app.core.logging import setup_logging
from app.core.paths import DASHBOARD_DIST_DIR

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
        )
    # /health stays tokenless so clients can show connection status pre-auth.
    app.include_router(health_routes.router, prefix=API_PREFIX)
    guarded = [Depends(require_token)]
    app.include_router(memory_routes.router, prefix=API_PREFIX, dependencies=guarded)
    app.include_router(context_routes.router, prefix=API_PREFIX, dependencies=guarded)
    app.include_router(episode_routes.router, prefix=API_PREFIX, dependencies=guarded)
    app.include_router(workspace_routes.router, prefix=API_PREFIX, dependencies=guarded)
    app.include_router(project_state_routes.router, prefix=API_PREFIX, dependencies=guarded)
    app.include_router(project_routes.router, prefix=API_PREFIX, dependencies=guarded)
    register_error_handlers(app)

    # Dashboard (Phase 6): served at /dashboard once built (`npm run build`
    # in dashboard/). Absent in dev, where Vite's own dev server is used
    # instead — this mount is a no-op until dist/ exists.
    if DASHBOARD_DIST_DIR.is_dir():
        app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIST_DIR, html=True), name="dashboard")

    return app


app = create_app()
