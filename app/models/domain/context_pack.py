"""Context Pack — the retrieval product handed to clients (architecture.md §7).

Rendered by the client into a prompt preamble; never the whole conversation.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Confidence, MemoryCategory
from app.utils.time import utc_now


class ContextMemory(BaseModel):
    """A single memory as it appears inside a Context Pack."""

    model_config = ConfigDict(frozen=True)

    category: MemoryCategory
    summary: str = Field(min_length=1)
    confidence: Confidence


class RecentConversation(BaseModel):
    """Sync-mode handoff excerpt: what the user was just discussing on another
    platform, so a new conversation inherits momentum, not only facts."""

    model_config = ConfigDict(frozen=True)

    platform: str
    minutes_ago: int = Field(ge=0)
    messages: list[str] = Field(default_factory=list)  # "User: …" / "Assistant: …"


class ContextSections(BaseModel):
    project_state: str | None = None
    profile: list[str] = Field(default_factory=list)
    relevant_memories: list[ContextMemory] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recent_conversation: RecentConversation | None = None  # sync mode only


class ContextPack(BaseModel):
    session_id: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=utc_now)
    # True when this pack contains only memories not yet injected into the session.
    delta: bool = False
    token_estimate: int = Field(default=0, ge=0)
    sections: ContextSections = Field(default_factory=ContextSections)
