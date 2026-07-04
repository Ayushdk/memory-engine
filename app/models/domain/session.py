"""A conversation session on some AI platform (chatgpt/claude/gemini/...),
and the raw messages that flow through it."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.utils.time import utc_now


@dataclass(frozen=True)
class ConversationMessage:
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = field(default_factory=utc_now)
    # Ingestion-time classification, persisted so downstream consumers (the
    # session recap) never re-classify: what the classifier decided and which
    # rule fired. None = pre-metadata snapshot or not yet classified.
    action: str | None = None
    matched_rule: str | None = None


class Session(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    project_id: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    last_activity_at: datetime = Field(default_factory=utc_now)
