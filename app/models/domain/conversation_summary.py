"""ConversationSummary — the rolling "Current Context Summary" for one session.

One evolving summary, chained forward: each summarization replaces it with
Summarize(previous summary + unsummarized raw messages). This is the
canonical conversation state injected on Sync; workspace/project summaries
are separate project knowledge and never replace it.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.utils.time import utc_now


class ConversationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    summary: str = ""
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_empty(self) -> bool:
        return not self.summary
