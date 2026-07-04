"""Application settings. Values can be overridden via environment or .env file."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENMEMORY_", env_file=".env", extra="ignore")

    app_name: str = "OpenMemory Engine"
    version: str = "0.2.0"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # Client security: token unset = auth disabled (local dev); origins empty = CORS deny-all.
    # The extension sets OPENMEMORY_API_TOKEN + OPENMEMORY_CORS_ORIGINS='["chrome-extension://<id>"]'.
    api_token: str | None = None
    cors_origins: list[str] = []

    # Strategy selection (architecture.md §4): rules is the only V1 implementation.
    classifier_strategy: Literal["rules", "ollama", "gemini"] = "rules"
    scorer_strategy: Literal["rules", "ollama", "gemini"] = "rules"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Working memory (architecture.md §4)
    working_memory_capacity: int = 30

    # Retrieval (architecture.md §4)
    retrieval_candidates: int = 40
    retrieval_top_k: int = 15

    # Context pack token budget (architecture.md §7)
    context_token_budget: int = 1500

    # Recent Session Recap (sync mode): source-session freshness window,
    # message window, and the recap's share of the total pack budget.
    recap_freshness_minutes: int = 30
    recap_max_messages: int = 12
    recap_budget_fraction: float = 0.20

    # Reflection triggers and thresholds (architecture.md §4)
    reflection_memory_threshold: int = 50
    dedup_similarity_threshold: float = 0.92
    update_similarity_threshold: float = 0.85


@lru_cache
def get_settings() -> Settings:
    return Settings()
