"""API request models for the context endpoint."""

from pydantic import BaseModel, Field


class ContextRequest(BaseModel):
    session_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    project_id: str | None = None
