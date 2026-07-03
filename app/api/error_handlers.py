"""Unexpected failures become structured 500s instead of raw tracebacks.

Pipeline-level failures (e.g. SQLite write errors) never reach here — they
come back as IngestionResult(success=False, ...) with a 200.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on {} {}: {}", request.method, request.url.path, exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})
