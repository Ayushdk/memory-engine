"""DI wiring: engine singletons live on app.state (architecture.md §8).

The SQLite connection is opened by the lifespan; everything else is built
lazily on first request and reused for the process lifetime.
"""

from fastapi import Request

from app.engine.classifier.memory_classifier import create_classifier
from app.engine.orchestrator.ingestion_pipeline import IngestionPipeline
from app.engine.router.storage_router import RuleStorageRouter
from app.engine.scorer.importance_scorer import create_scorer
from app.engine.working_memory.working_memory_manager import WorkingMemoryManager
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.vector.chroma_client import ChromaVectorStore
from app.services.embedding_service import get_embedding_service


def get_ingestion_pipeline(request: Request) -> IngestionPipeline:
    state = request.app.state
    if getattr(state, "ingestion_pipeline", None) is None:
        state.ingestion_pipeline = IngestionPipeline(
            working_memory=WorkingMemoryManager(),
            classifier=create_classifier(),
            scorer=create_scorer(),
            router=RuleStorageRouter(),
            repository=MemoryRepository(state.db),
            vector_store=ChromaVectorStore(),
            embedding_service=get_embedding_service(),
        )
    return state.ingestion_pipeline
