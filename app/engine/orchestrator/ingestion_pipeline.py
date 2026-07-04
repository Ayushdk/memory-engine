"""Ingestion Orchestrator (architecture.md §2, §4): WM → classify → score →
route → store. Coordination only — every decision lives in the module that
owns it. SQLite is written FIRST (source of truth), Chroma SECOND (index);
a Chroma failure leaves the result `sqlite_only`, repairable by reset_db.py.
"""

from dataclasses import dataclass
from typing import Literal

from loguru import logger

from app.core.config import get_settings
from app.engine.classifier.memory_classifier import ClassificationResult, MemoryClassifier
from app.engine.router.storage_router import RoutingResult, StorageRouter
from app.engine.scorer.importance_scorer import ImportanceScorer, ScoringResult
from app.engine.working_memory.persistence import PersistentWorkingMemory
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.vector.chroma_client import ChromaVectorStore, active_where
from app.models.domain.memory import Memory, Source
from app.models.enums import ClassifierAction, Confidence, MemoryStatus
from app.services.embedding_service import EmbeddingService

SyncStatus = Literal["skipped", "in_sync", "sqlite_only", "failed"]


@dataclass(frozen=True)
class IngestionResult:
    action: ClassifierAction
    success: bool
    synchronization_status: SyncStatus
    memory_id: str | None = None
    classification: ClassificationResult | None = None
    scoring: ScoringResult | None = None
    routing: RoutingResult | None = None
    reasoning: str | None = None


class IngestionPipeline:
    def __init__(
        self,
        working_memory: PersistentWorkingMemory,
        classifier: MemoryClassifier,
        scorer: ImportanceScorer,
        router: StorageRouter,
        repository: MemoryRepository,
        vector_store: ChromaVectorStore,
        embedding_service: EmbeddingService,
    ) -> None:
        self._working_memory = working_memory
        self._classifier = classifier
        self._scorer = scorer
        self._router = router
        self._repository = repository
        self._vector_store = vector_store
        self._embeddings = embedding_service

    def ingest(
        self,
        session_id: str,
        platform: str,
        role: Literal["user", "assistant"],
        content: str,
        project_id: str | None = None,
    ) -> IngestionResult:
        self._working_memory.add_message(
            session_id, role, content, platform=platform, project_id=project_id
        )

        classification = self._classifier.classify(
            content, self._working_memory.get_messages(session_id)
        )

        if classification.action is ClassifierAction.IGNORE:
            return IngestionResult(
                action=ClassifierAction.IGNORE,
                success=True,
                synchronization_status="skipped",
                classification=classification,
                reasoning=classification.reason,
            )

        if classification.action in (ClassifierAction.DELETE, ClassifierAction.MERGE):
            # ponytail: delete targeting + merge live in Phase 5 reflection / the
            # DELETE endpoint; a command message itself is never stored as a memory.
            return IngestionResult(
                action=classification.action,
                success=True,
                synchronization_status="skipped",
                classification=classification,
                reasoning=f"{classification.action} commands are handled outside ingestion in V1",
            )

        scoring = self._scorer.score(classification, content, project_id)
        routing = self._router.route(classification, scoring, content, project_id)

        embedding = self._embeddings.embed(content)

        superseded_id = None
        if classification.action is ClassifierAction.UPDATE:
            superseded_id = self._find_update_target(embedding, project_id)

        memory = Memory(
            content=content,
            category=classification.category,
            view=routing.view,
            project_id=project_id,
            importance=scoring.importance,
            confidence=Confidence.HIGH,  # rules only match explicit statements (decision #7)
            supersedes=superseded_id,
            source=Source(platform=platform, session_id=session_id, role=role),
        )

        # SQLite FIRST — source of truth. Any failure stops the pipeline here.
        try:
            self._repository.save(memory)
            if superseded_id:
                self._repository.set_status(superseded_id, MemoryStatus.SUPERSEDED)
        except Exception as exc:
            logger.error("SQLite write failed for {}: {}", memory.id, exc)
            return IngestionResult(
                action=classification.action,
                success=False,
                synchronization_status="failed",
                classification=classification,
                scoring=scoring,
                routing=routing,
                reasoning=f"sqlite write failed: {exc}",
            )

        # Chroma SECOND — index only; on failure SQLite stays correct.
        sync: SyncStatus = "in_sync"
        try:
            self._vector_store.upsert(memory, embedding)
            if superseded_id:
                self._vector_store.update_status(superseded_id, MemoryStatus.SUPERSEDED.value)
        except Exception as exc:
            logger.warning("Chroma out of sync for {} (run reset_db.py): {}", memory.id, exc)
            sync = "sqlite_only"

        return IngestionResult(
            action=classification.action,
            success=True,
            synchronization_status=sync,
            memory_id=memory.id,
            classification=classification,
            scoring=scoring,
            routing=routing,
            reasoning=(
                f"supersedes {superseded_id}" if superseded_id
                else "stored as new memory" if classification.action is ClassifierAction.UPDATE
                else None
            ),
        )

    def _find_update_target(self, embedding: list[float], project_id: str | None) -> str | None:
        """Most similar ACTIVE memory above the config threshold, else None
        (unconfirmed updates fall back to a plain store)."""
        candidates = self._vector_store.query(
            embedding, n_results=1, where=active_where(project_id)
        )
        if candidates:
            memory_id, similarity = candidates[0]
            if similarity >= get_settings().update_similarity_threshold:
                return memory_id
        return None
