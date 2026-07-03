"""Per-session conversation state: raw messages, not Memory objects."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.utils.time import utc_now


@dataclass(frozen=True)
class ConversationMessage:
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = field(default_factory=utc_now)
