"""Ollama provider — plain REST on localhost, no SDK dependency.

Structured output: the caller's JSON schema is passed as Ollama's `format`
parameter, so generation is grammar-constrained server-side. jsonschema
re-validates client-side anyway because callers persist this output — the
LLM proposes, deterministic code disposes.
"""

import json

import httpx
import jsonschema

from app.engine.llm.provider import ProviderError, ProviderHealth
from app.services.tokenizer_service import estimate_tokens

# Health probes must answer fast even when generation timeouts are generous.
HEALTH_TIMEOUT_SECONDS = 3.0

# ponytail: Ollama defaults num_ctx to 2048 and silently drops whatever
# doesn't fit — no error, just a quietly truncated prompt (this is what made
# long assistant turns vanish from the rolling conversation summary even
# though the full text was stored correctly). Size the context window to the
# actual prompt instead of trusting the server default.
MIN_NUM_CTX = 4096


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        url: str,
        model: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._url = url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._transport = transport  # tests inject httpx.MockTransport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    async def generate(self, prompt: str, output_schema: dict) -> dict:
        try:
            async with self._client(self._timeout) as client:
                response = await client.post(
                    f"{self._url}/api/chat",
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "format": output_schema,
                        "stream": False,
                        # extraction must be repeatable, not creative
                        "options": {
                            "temperature": 0,
                            # size to the actual prompt — Ollama's 2048-token
                            # default silently drops overflow instead of erroring
                            "num_ctx": max(MIN_NUM_CTX, estimate_tokens(prompt) + 512),
                        },
                    },
                )
                response.raise_for_status()
            data = json.loads(response.json()["message"]["content"])
            jsonschema.validate(data, output_schema)
        except httpx.HTTPError as exc:
            raise ProviderError(f"ollama request failed: {exc}") from exc
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"ollama returned a malformed response: {exc}") from exc
        except jsonschema.ValidationError as exc:
            raise ProviderError(f"ollama output failed schema validation: {exc.message}") from exc
        return data

    async def health(self) -> ProviderHealth:
        try:
            async with self._client(HEALTH_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self._url}/api/tags")
                response.raise_for_status()
                models = [m.get("name", "") for m in response.json().get("models", [])]
        except (httpx.HTTPError, ValueError) as exc:
            return ProviderHealth(
                False, self.name, self._model, f"server unreachable at {self._url}: {exc}"
            )
        # "qwen2.5" in config matches the "qwen2.5:3b" tag Ollama reports
        if not any(name == self._model or name.split(":")[0] == self._model for name in models):
            return ProviderHealth(
                False,
                self.name,
                self._model,
                f"model not pulled (available: {', '.join(models) or 'none'})",
            )
        return ProviderHealth(True, self.name, self._model, "ready")
