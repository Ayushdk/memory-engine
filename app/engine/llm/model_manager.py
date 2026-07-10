"""Model provisioning — the engine ensures its own models exist in Ollama.

Deployment-agnostic auto-pull: whether Ollama came from Docker Compose, a
native install, or a future OpenMemory CLI, the engine checks /api/tags at
startup and pulls whatever the configured roles need via /api/pull. Compose
stays dumb (starts an empty Ollama); provisioning lives here, once.

Fire-and-forget from the app lifespan; never blocks startup, never raises.
`pull_status()` is surfaced by /health so clients can show "preparing
models…" instead of a dead intelligence feature.
"""

import asyncio

import httpx
from loguru import logger

from app.core.config import Settings

# ponytail: coarse per-model status, no percentage; parse /api/pull's NDJSON
# stream for progress % if the dashboard ever wants a bar.
_PULL_STATUS: dict[str, str] = {}  # model -> "pulling" | "ready" | "failed: <reason>"

# Pulls are multi-GB; only connect/read inactivity should time out, not the
# download itself.
_PULL_TIMEOUT = httpx.Timeout(connect=10, read=300, write=30, pool=10)


def pull_status() -> dict[str, str]:
    return dict(_PULL_STATUS)


async def _wait_for_server(client: httpx.AsyncClient, url: str, attempts: int, interval: float):
    """Compose may still be starting Ollama; retry before giving up. Returns
    the pulled-model names, or None if the server never answered."""
    for attempt in range(attempts):
        try:
            response = await client.get(f"{url}/api/tags")
            response.raise_for_status()
            return [m.get("name", "") for m in response.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            if attempt < attempts - 1:
                await asyncio.sleep(interval)
    return None


async def ensure_models(
    settings: Settings,
    *,
    attempts: int = 30,
    interval: float = 2.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    if settings.llm_provider != "ollama" or not settings.ollama_auto_pull:
        return
    url = settings.ollama_url.rstrip("/")
    wanted = {settings.ollama_summarizer_model, settings.ollama_reasoner_model}

    async with httpx.AsyncClient(timeout=_PULL_TIMEOUT, transport=transport) as client:
        present = await _wait_for_server(client, url, attempts, interval)
        if present is None:
            logger.warning("Ollama unreachable at {} — skipping model auto-pull", url)
            return
        missing = [
            m
            for m in sorted(wanted)
            if not any(name == m or name.split(":")[0] == m for name in present)
        ]
        for model in missing:
            _PULL_STATUS[model] = "pulling"
            logger.info("Pulling missing model {} (this can take minutes)", model)
            try:
                # stream=True: progress lines keep bytes flowing, so the read
                # timeout only fires on a genuine stall — stream=False sends
                # nothing until the multi-GB pull finishes and would time out.
                async with client.stream(
                    "POST", f"{url}/api/pull", json={"model": model, "stream": True}
                ) as response:
                    response.raise_for_status()
                    async for _ in response.aiter_lines():
                        pass
                _PULL_STATUS[model] = "ready"
                logger.info("Model {} ready", model)
            except httpx.HTTPError as exc:
                _PULL_STATUS[model] = f"failed: {exc}"
                logger.warning("Model pull failed for {}: {}", model, exc)
