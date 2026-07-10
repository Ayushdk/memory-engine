"""Engine-owned model provisioning: auto-pull missing role models at startup."""

import httpx
import pytest

from app.core.config import Settings
from app.engine.llm import model_manager
from app.engine.llm.model_manager import ensure_models, pull_status


@pytest.fixture(autouse=True)
def clean_status():
    model_manager._PULL_STATUS.clear()
    yield
    model_manager._PULL_STATUS.clear()


def settings_with(**overrides):
    defaults = dict(
        _env_file=None,
        llm_provider="ollama",
        ollama_summarizer_model="qwen2.5:3b",
        ollama_reasoner_model="qwen3:8b",
    )
    return Settings(**{**defaults, **overrides})


def ollama(models=(), pull_response=200):
    """Fake Ollama recording every pull it receives."""
    pulled = []

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        if request.url.path == "/api/pull":
            pulled.append(request.read().decode())
            return httpx.Response(pull_response, json={"status": "success"})
        raise AssertionError(f"unexpected call: {request.url.path}")

    return httpx.MockTransport(handler), pulled


async def test_noop_when_provider_disabled():
    def explode(request):
        raise AssertionError("must not touch the network when provider is none")

    await ensure_models(
        settings_with(llm_provider="none"), transport=httpx.MockTransport(explode)
    )


async def test_pulls_only_missing_models():
    transport, pulled = ollama(models=["qwen2.5:3b"])  # summarizer present
    await ensure_models(settings_with(), transport=transport)
    assert len(pulled) == 1 and "qwen3:8b" in pulled[0]
    assert pull_status() == {"qwen3:8b": "ready"}


async def test_base_name_counts_as_present():
    transport, pulled = ollama(models=["qwen2.5:3b", "qwen3:8b"])
    await ensure_models(settings_with(ollama_reasoner_model="qwen3"), transport=transport)
    assert pulled == []


async def test_failed_pull_is_recorded_not_raised():
    transport, _ = ollama(models=[], pull_response=500)
    await ensure_models(settings_with(), transport=transport)
    assert all(v.startswith("failed:") for v in pull_status().values())
    assert set(pull_status()) == {"qwen2.5:3b", "qwen3:8b"}


async def test_unreachable_server_gives_up_quietly():
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    await ensure_models(
        settings_with(),
        attempts=2,
        interval=0,
        transport=httpx.MockTransport(refuse),
    )
    assert pull_status() == {}


async def test_health_reports_pull_in_progress(monkeypatch):
    from app.api.routes import health_routes

    model_manager._PULL_STATUS["qwen3:8b"] = "pulling"

    def down(request):
        return httpx.Response(200, json={"models": []})  # server up, model absent

    monkeypatch.setattr(health_routes, "get_settings", lambda: settings_with())
    monkeypatch.setattr(
        health_routes,
        "create_provider",
        lambda role, settings: __import__(
            "app.engine.llm.ollama_provider", fromlist=["OllamaProvider"]
        ).OllamaProvider(
            url="http://x",
            model="qwen3:8b" if role == "reasoner" else "qwen2.5:3b",
            timeout=5,
            transport=httpx.MockTransport(down),
        ),
    )
    body = await health_routes.health()
    assert body["intelligence"]["reasoner"]["detail"] == "model downloading (auto-pull in progress)"
    assert "not pulled" in body["intelligence"]["summarizer"]["detail"]  # no pull recorded
