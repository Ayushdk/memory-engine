"""API request models for the context endpoint."""

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class ContextRequest(BaseModel):
    session_id: str = Field(min_length=1)
    # query mode: mid-conversation retrieval. sync mode: the extension's
    # "Sync Context" button — state-driven snapshot, no query.
    mode: Literal["query", "sync"] = "query"
    query: str | None = Field(default=None, min_length=1)
    project_id: str | None = None
    # sync mode default-excludes brain content (profile/long-term memories/
    # dashboard state) per the injection rules — only the latest working
    # summary, project context, and task state go out unless asked for more.
    include_brain: bool = False

    @model_validator(mode="after")
    def _query_matches_mode(self) -> Self:
        if self.mode == "query" and self.query is None:
            raise ValueError("query is required in query mode")
        if self.mode == "sync" and self.query is not None:
            raise ValueError("sync mode does not accept a query")
        return self
