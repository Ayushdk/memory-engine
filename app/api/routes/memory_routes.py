"""Memory routes — transport only. Validate, resolve dependencies, delegate."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_ingestion_pipeline
from app.engine.orchestrator.ingestion_pipeline import IngestionPipeline, IngestionResult
from app.models.schemas.memory_requests import IngestRequest

router = APIRouter(tags=["memory"])


@router.post("/ingest")
def ingest(
    request: IngestRequest,
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
) -> IngestionResult:
    return pipeline.ingest(**request.model_dump())
