"""LLM provider seam: factory, Ollama structured output, health, degradation.

Ollama is mocked via httpx.MockTransport — no server needed. The live
small-model quality gate lives in scripts/llm_spotcheck.py, judged by eye.
"""

import json

import httpx
import pytest

from app.core.config import Settings
from app.engine.llm.ollama_provider import OllamaProvider
from app.engine.llm.provider import NO_PROVIDER, ProviderError, create_provider

SCHEMA = {
    "type": "object",
    "properties": {"memories": {"type": "array", "items": {"type": "string"}}},
    "required": ["memories"],
}


def provider_with(handler, model="qwen2.5:3b"):
    return OllamaProvider(
        url="http://127.0.0.1:11434",
        model=model,
        timeout=5,
        transport=httpx.MockTransport(handler),
    )


def chat_reply(content: str):
    """Ollama /api/chat handler that also asserts the request contract."""

    def handler(request):
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["format"] == SCHEMA
        assert body["stream"] is False
        assert body["options"]["temperature"] == 0
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    return handler


def tags_reply(*names):
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": n} for n in names]})

    return handler


class TestFactory:
    def test_unconfigured_returns_none_for_every_role(self):
        settings = Settings(_env_file=None, llm_provider="none")
        assert create_provider("summarizer", settings) is None
        assert create_provider("reasoner", settings) is None

    def test_roles_select_their_configured_models(self):
        settings = Settings(
            _env_file=None,
            llm_provider="ollama",
            ollama_summarizer_model="gemma3:4b",
            ollama_reasoner_model="qwen3:8b",
        )
        summarizer = create_provider("summarizer", settings)
        reasoner = create_provider("reasoner", settings)
        assert isinstance(summarizer, OllamaProvider)
        assert summarizer._model == "gemma3:4b"
        assert reasoner._model == "qwen3:8b"

    def test_no_provider_health_constant(self):
        assert NO_PROVIDER.available is False
        assert NO_PROVIDER.provider == "none"


class TestGenerate:
    async def test_returns_schema_valid_dict(self):
        provider = provider_with(chat_reply('{"memories": ["SQLite is the source of truth"]}'))
        result = await provider.generate("extract", SCHEMA)
        assert result == {"memories": ["SQLite is the source of truth"]}

    async def test_system_prompt_sent_as_its_own_message(self):
        def handler(request):
            body = json.loads(request.content)
            assert body["messages"] == [
                {"role": "system", "content": "be terse"},
                {"role": "user", "content": "extract"},
            ]
            return httpx.Response(200, json={"message": {"content": '{"memories": []}'}})

        provider = provider_with(handler)
        await provider.generate("extract", SCHEMA, system="be terse")

    async def test_no_system_message_when_system_is_none(self):
        def handler(request):
            body = json.loads(request.content)
            assert body["messages"] == [{"role": "user", "content": "extract"}]
            return httpx.Response(200, json={"message": {"content": '{"memories": []}'}})

        provider = provider_with(handler)
        await provider.generate("extract", SCHEMA)

    async def test_rejects_schema_violation(self):
        provider = provider_with(chat_reply('{"memories": "not a list"}'))
        with pytest.raises(ProviderError, match="schema validation"):
            await provider.generate("extract", SCHEMA)

    async def test_rejects_non_json_content(self):
        provider = provider_with(chat_reply("I am prose, not JSON"))
        with pytest.raises(ProviderError, match="malformed"):
            await provider.generate("extract", SCHEMA)

    async def test_wraps_http_errors(self):
        provider = provider_with(lambda request: httpx.Response(500, text="boom"))
        with pytest.raises(ProviderError, match="request failed"):
            await provider.generate("extract", SCHEMA)

    async def test_wraps_connection_errors(self):
        def refuse(request):
            raise httpx.ConnectError("connection refused")

        with pytest.raises(ProviderError, match="request failed"):
            await provider_with(refuse).generate("extract", SCHEMA)


class TestHealth:
    async def test_ready_when_model_pulled(self):
        health = await provider_with(tags_reply("qwen2.5:3b", "llama3.2:3b")).health()
        assert health == health.__class__(True, "ollama", "qwen2.5:3b", "ready")

    async def test_base_name_matches_tagged_model(self):
        health = await provider_with(tags_reply("qwen2.5:3b"), model="qwen2.5").health()
        assert health.available is True

    async def test_unavailable_when_model_missing(self):
        health = await provider_with(tags_reply("llama3.2:3b")).health()
        assert health.available is False
        assert "llama3.2:3b" in health.detail  # tells the user what IS pulled

    async def test_unavailable_when_server_down(self):
        def refuse(request):
            raise httpx.ConnectError("connection refused")

        health = await provider_with(refuse).health()
        assert health.available is False
        assert "unreachable" in health.detail


class TestHealthEndpoint:
    async def test_reports_intelligence_disabled_by_default(self, monkeypatch):
        from app.api.routes import health_routes

        monkeypatch.setattr(
            health_routes, "get_settings", lambda: Settings(_env_file=None, llm_provider="none")
        )
        body = await health_routes.health()
        assert body["status"] == "ok"
        disabled = {
            "available": False,
            "provider": "none",
            "model": None,
            "detail": "no LLM provider configured",
        }
        assert body["intelligence"] == {"summarizer": disabled, "reasoner": disabled}
