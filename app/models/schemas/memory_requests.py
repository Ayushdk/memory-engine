"""API request models — transport shapes only, never imported by the engine."""

from typing import Literal

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    session_id: str = Field(min_length=1)
    platform: str = Field(min_length=1, examples=["chatgpt", "claude", "gemini"])
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    project_id: str | None = None
    # Lightweight session metadata (e.g. the conversation title); optional.
    title: str | None = None
