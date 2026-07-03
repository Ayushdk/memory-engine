"""Project — groups memories and carries the consolidated Project State."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProjectStatus
from app.utils.ids import new_project_id
from app.utils.time import utc_now


class Project(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=new_project_id)
    name: str = Field(min_length=1)
    status: ProjectStatus = ProjectStatus.ACTIVE

    # Consolidated Project State, rebuilt by the Reflection path (architecture.md §4).
    # Shape is owned by the consolidation engine (Phase 5); the domain only carries it.
    state: dict[str, Any] | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
