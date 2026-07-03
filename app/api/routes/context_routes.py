"""Context routes — transport only. Validate, resolve dependencies, delegate."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_context_pipeline
from app.engine.orchestrator.context_pipeline import ContextPipeline
from app.models.domain.context_pack import ContextPack
from app.models.schemas.context_requests import ContextRequest

router = APIRouter(tags=["context"])


@router.post("/context")
def context(
    request: ContextRequest,
    pipeline: Annotated[ContextPipeline, Depends(get_context_pipeline)],
) -> ContextPack:
    return pipeline.build_context(**request.model_dump())
