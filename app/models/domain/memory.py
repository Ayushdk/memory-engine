"""The Memory object — the single schema every module shares (architecture.md §3).

The embedding is NOT stored here; it lives in ChromaDB keyed by the same id.
"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import Confidence, MemoryCategory, MemoryStatus, MemoryView
from app.utils.ids import new_memory_id
from app.utils.time import utc_now


class Source(BaseModel):
    """Where a memory came from: which platform, session, and speaker."""

    model_config = ConfigDict(frozen=True)

    platform: str = Field(min_length=1, description="e.g. 'chatgpt', 'claude', 'gemini'")
    session_id: str | None = None
    role: Literal["user", "assistant"] = "user"
    # Provenance for extracted memories: the episode whose distilled Workspace
    # State produced this memory (decision #10: episodes it references are
    # pinned, never pruned).
    episode_id: str | None = None


class Memory(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=new_memory_id)
    content: str = Field(min_length=1)
    summary: str | None = None

    category: MemoryCategory
    view: MemoryView
    project_id: str | None = None

    importance: int = Field(ge=0, le=10)
    confidence: Confidence
    status: MemoryStatus = MemoryStatus.ACTIVE
    # Non-destructive update: this memory replaces the referenced one,
    # which is then marked MemoryStatus.SUPERSEDED.
    supersedes: str | None = None

    source: Source | None = None
    tags: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    # Written by the Retrieval Engine; feed reflection (decay, dedup priority).
    last_accessed_at: datetime | None = None
    access_count: int = Field(default=0, ge=0)

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, tags: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for tag in tags:
            cleaned = tag.strip().lower()
            if cleaned:
                seen.setdefault(cleaned, None)
        return list(seen)

    @model_validator(mode="after")
    def _project_view_requires_project(self) -> Self:
        if self.view is MemoryView.PROJECT and self.project_id is None:
            raise ValueError("a memory in the 'project' view must have a project_id")
        return self
