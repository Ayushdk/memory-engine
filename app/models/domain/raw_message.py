"""A RawMessage: one exchanged message, kept forever (never deleted).

The append-only evidence ledger beneath episodes/summaries. Episodes
summarize a time window of these and flip `summarized`; the row itself is
never removed, so the complete conversation history always survives
independent of how many summary generations have run over it.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.utils.ids import new_raw_message_id
from app.utils.time import utc_now


class RawMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=new_raw_message_id)
    session_id: str = Field(min_length=1)
    project_id: str | None = None
    platform: str = "unknown"
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=utc_now)
    summarized: bool = False
