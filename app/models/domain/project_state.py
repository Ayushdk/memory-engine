"""Project State — a versioned, synthesized snapshot of a project's highest-
quality active knowledge (intelligence-layer.md §7). Never overwritten: each
reflection cycle that produces a materially different picture appends a new
version. Latest version is the active overview.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.utils.ids import new_project_state_id
from app.utils.time import utc_now


class ProjectState(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=new_project_state_id)
    project_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    content: str = Field(min_length=1)
    # Memory ids this version was synthesized from (provenance, not re-read).
    generated_from: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
