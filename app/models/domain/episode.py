"""An Episode: one contiguous segment of a conversation (intelligence-layer.md §4).

Episodes are the unit of summarization and extraction. Boundaries are
deterministic (inactivity, message cap, Sync); a closed episode is
summarized asynchronously and becomes the source for workspace updates and
the semantic pipeline.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.utils.ids import new_episode_id
from app.utils.time import utc_now

EpisodeStatus = Literal["open", "closed", "summarized"]
BoundaryReason = Literal["message-cap", "inactivity", "sync"]


class Episode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=new_episode_id)
    session_id: str = Field(min_length=1)
    project_id: str | None = None
    platform: str | None = None
    status: EpisodeStatus = "open"
    boundary_reason: str | None = None
    message_count: int = 0
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    summary_internal: str | None = None
