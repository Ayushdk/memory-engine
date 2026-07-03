"""Memory routes — transport only. Validate, resolve dependencies, delegate."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_ingestion_pipeline, get_memory_repository
from app.engine.orchestrator.ingestion_pipeline import IngestionPipeline, IngestionResult
from app.memory.repositories.memory_repository import MemoryRepository
from app.models.enums import MemoryCategory, MemoryStatus, MemoryView
from app.models.schemas.memory_requests import IngestRequest
from app.models.schemas.memory_responses import MemoryListResponse

router = APIRouter(tags=["memory"])


@router.get("/memories")
def list_memories(
    repository: Annotated[MemoryRepository, Depends(get_memory_repository)],
    view: MemoryView | None = None,
    project_id: str | None = None,
    category: MemoryCategory | None = None,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> MemoryListResponse:
    memories = repository.list(
        view=view, project_id=project_id, category=category, status=status, limit=limit
    )
    return MemoryListResponse(memories=memories, count=len(memories))


@router.post("/ingest")
def ingest(
    request: IngestRequest,
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
) -> IngestionResult:
    return pipeline.ingest(**request.model_dump())
