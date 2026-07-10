import asyncio
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.engine.llm.provider import NO_PROVIDER, create_provider

router = APIRouter(tags=["health"])


async def _role_health(role, settings):
    provider = create_provider(role, settings)
    return asdict(await provider.health() if provider else NO_PROVIDER)


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
