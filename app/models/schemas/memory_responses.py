"""API response models for memory browsing."""

from pydantic import BaseModel

from app.models.domain.memory import Memory


class MemoryListResponse(BaseModel):
    memories: list[Memory]
    count: int
