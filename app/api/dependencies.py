"""DI wiring: engine singletons live on app.state (architecture.md §8).

The SQLite connection is opened by the lifespan; everything else is built
lazily on first request and reused for the process lifetime. Both pipelines
share one repository and one vector store.
"""

from fastapi import Request

from app.engine.classifier.memory_classifier import create_classifier
from app.engine.context.context_builder import ContextBuilder
from app.engine.orchestrator.context_pipeline import ContextPipeline
from app.engine.orchestrator.ingestion_pipeline import IngestionPipeline
from app.engine.orchestrator.memory_admin import MemoryAdmin
from app.engine.retrieval.ranking_engine import RankingEngine
from app.engine.retrieval.retrieval_engine import RetrievalEngine
from app.engine.router.storage_router import RuleStorageRouter
from app.engine.scorer.importance_scorer import create_scorer
from app.engine.working_memory.working_memory_manager import WorkingMemoryManager
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.vector.chroma_client import ChromaVectorStore
from app.services.embedding_service import get_embedding_service


def _get_repository(state) -> MemoryRepository:
    if getattr(state, "memory_repository", None) is None:
        state.memory_repository = MemoryRepository(state.db)
    return state.memory_repository


def _get_vector_store(state) -> ChromaVectorStore:
    if getattr(state, "vector_store", None) is None:
        state.vector_store = ChromaVectorStore()
    return state.vector_store


def get_memory_repository(request: Request) -> MemoryRepository:
    return _get_repository(request.app.state)


def get_memory_admin(request: Request) -> MemoryAdmin:
    state = request.app.state
    if getattr(state, "memory_admin", None) is None:
        state.memory_admin = MemoryAdmin(_get_repository(state), _get_vector_store(state))
    return state.memory_admin


def get_ingestion_pipeline(request: Request) -> IngestionPipeline:
    state = request.app.state
    if getattr(state, "ingestion_pipeline", None) is None:
        state.ingestion_pipeline = IngestionPipeline(
            working_memory=WorkingMemoryManager(),
            classifier=create_classifier(),
            scorer=create_scorer(),
            router=RuleStorageRouter(),
            repository=_get_repository(state),
            vector_store=_get_vector_store(state),
            embedding_service=get_embedding_service(),
        )
    return state.ingestion_pipeline


def get_context_pipeline(request: Request) -> ContextPipeline:
    state = request.app.state
    if getattr(state, "context_pipeline", None) is None:
        state.context_pipeline = ContextPipeline(
            retrieval_engine=RetrievalEngine(
                get_embedding_service(), _get_vector_store(state), _get_repository(state)
            ),
            ranking_engine=RankingEngine(),
            context_builder=ContextBuilder(),
            repository=_get_repository(state),
        )
    return state.context_pipeline
