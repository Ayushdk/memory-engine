"""Capture reset — discard a session's not-yet-processed capture.

The extension's Reset button lands here. Scope is strictly "what no summary
has consumed yet": unsummarized raw messages, the open episode, and the live
working-memory buffer. Conversation summaries, workspaces, project state,
memories, and all summarized history are untouched.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from loguru import logger

from app.api.dependencies import (
    get_episode_repository,
    get_ingestion_pipeline,
    get_raw_message_repository,
)
from app.engine.orchestrator.ingestion_pipeline import IngestionPipeline
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.raw_message_repository import RawMessageRepository

router = APIRouter(tags=["capture"])


@router.post("/capture/{session_id}/reset")
def reset_capture(
    session_id: str,
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
    episodes: Annotated[EpisodeRepository, Depends(get_episode_repository)],
    raw_messages: Annotated[RawMessageRepository, Depends(get_raw_message_repository)],
) -> dict:
    discarded_messages = raw_messages.delete_unsummarized(session_id)
    discarded_episode = episodes.delete_open(session_id)
    pipeline.working_memory.clear(session_id)
    logger.info(
        "capture reset session={} raw_messages_discarded={} episode_discarded={}",
        session_id, discarded_messages, discarded_episode,
    )
    return {
        "session_id": session_id,
        "raw_messages_discarded": discarded_messages,
        "episode_discarded": discarded_episode,
    }
