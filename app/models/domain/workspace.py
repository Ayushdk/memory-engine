"""Workspace — the current working state of one project (intelligence-layer §3.3).

Three related artifacts, one storage concern here:
- Workspace State: internal working notes + goal + blockers (this model)
- Transfer Summary: compact, token-budgeted briefing for AI handoff (field)
- Workspace Timeline: chronological episode history — NOT stored here, it
  derives from the episodes table.

Volatile by design: updated continuously as episodes close; reset or
archived by the user; never a memory database.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.utils.time import utc_now


class Workspace(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str = Field(min_length=1)
    internal_summary: str = ""
    transfer_summary: str = ""
    goal: str | None = None
    blockers: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_empty(self) -> bool:
        return not (self.internal_summary or self.transfer_summary or self.goal or self.blockers)


class WorkspaceArchive(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    project_id: str
    internal_summary: str
    transfer_summary: str
    goal: str | None
    blockers: list[str]
    archived_at: datetime
