"""LLM provider — the intelligence layer's only formal interface.

Swap seam (intelligence-layer.md §8): extraction, reflection, and
project-state synthesis call `generate(prompt, output_schema)` and never know
which model runs. Ollama today; bigger local or opt-in cloud models later,
behind this same Protocol.

No provider configured → `create_provider` returns None and intelligence
features no-op: the engine keeps its V1 heuristic behavior (locked decision
#3, graceful degradation).
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.config import Settings, get_settings

# Different models for different jobs (intelligence-layer.md v2): episode /
# workspace summarization runs constantly and must be light; extraction,
# reflection, and synthesis need the heavier reasoner.
Role = Literal["summarizer", "reasoner"]


class ProviderError(Exception):
    """Provider failed to produce schema-valid output.

    Callers skip the pass and degrade — never persist partial results
    (intelligence-layer.md locked decision #2).
    """


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    provider: str
    model: str | None
    detail: str


NO_PROVIDER = ProviderHealth(
    available=False, provider="none", model=None, detail="no LLM provider configured"
)


class LLMProvider(Protocol):
    async def generate(
        self, prompt: str, output_schema: dict, system: str | None = None
    ) -> dict:
        """Return a dict validated against output_schema, or raise ProviderError."""
        ...

    async def health(self) -> ProviderHealth: ...


def create_provider(role: Role, settings: Settings | None = None) -> LLMProvider | None:
    settings = settings or get_settings()
    if settings.llm_provider == "ollama":
        from app.engine.llm.ollama_provider import OllamaProvider

        model = (
            settings.ollama_summarizer_model
            if role == "summarizer"
            else settings.ollama_reasoner_model
        )
        return OllamaProvider(
            url=settings.ollama_url,
            model=model,
            timeout=settings.ollama_timeout_seconds,
        )
    return None
