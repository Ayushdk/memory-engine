import asyncio
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.engine.llm.model_manager import pull_status
from app.engine.llm.provider import NO_PROVIDER, create_provider

router = APIRouter(tags=["health"])


async def _role_health(role, settings):
    provider = create_provider(role, settings)
    health = asdict(await provider.health() if provider else NO_PROVIDER)
    # Auto-pull in flight beats "model not pulled": tell clients it's coming.
    status = pull_status().get(health["model"])
    if not health["available"] and status == "pulling":
        health["detail"] = "model downloading (auto-pull in progress)"
    return health


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    summarizer, reasoner = await asyncio.gather(
        _role_health("summarizer", settings), _role_health("reasoner", settings)
    )
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "time": datetime.now(timezone.utc).isoformat(),
        "intelligence": {"summarizer": summarizer, "reasoner": reasoner},
    }
