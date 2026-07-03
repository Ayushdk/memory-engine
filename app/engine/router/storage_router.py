"""Storage Router — assigns the logical MemoryView (architecture.md §4).

Views are Gmail-style labels over the ONE unified memory store (locked
decision #2); the router never chooses a database. Deterministic mapping:
category × project × pronoun heuristics. Rules are checked in order; the
first hit wins:

1. personal facts about the user → PROFILE (they transcend any project)
2. project_id present → PROJECT
3. session-bound events (meetings, milestones) → EPISODIC
4. explicitly transient, unanchored context → WORKING
5. everything else (research, concepts, learning) → SEMANTIC

Note: §4 mentions the router "writes SQLite first, Chroma second" — that
write *ordering* is enforced by the ingestion orchestrator (step 5); this
module stays persistence-free by design so it remains a pure function.
"""

from dataclasses import dataclass
from typing import Protocol

from app.engine.classifier.memory_classifier import ClassificationResult
from app.engine.scorer.importance_scorer import ScoringResult
from app.models.enums import MemoryCategory, MemoryView


@dataclass(frozen=True)
class RoutingResult:
    view: MemoryView
    matched_rule: str
    reasoning: str | None = None


class StorageRouter(Protocol):
    def route(
        self,
        classification: ClassificationResult,
        scoring: ScoringResult,
        message: str,
        project_id: str | None = None,
    ) -> RoutingResult: ...


# Pronoun heuristics for personal facts (first-person, about the user).
_PERSONAL_PREFIXES: tuple[str, ...] = (
    "i prefer",
    "i like",
    "i love",
    "i hate",
    "i'd rather",
    "i am",
    "i'm",
    "my ",
)

_EPISODIC_CATEGORIES = frozenset({MemoryCategory.MEETING, MemoryCategory.MILESTONE})


class RuleStorageRouter:
    """Deterministic view assignment. No persistence, no embeddings."""

    def route(
        self,
        classification: ClassificationResult,
        scoring: ScoringResult,
        message: str,
        project_id: str | None = None,
    ) -> RoutingResult:
        normalized = message.strip().lower()

        if classification.category is MemoryCategory.PREFERENCE or normalized.startswith(
            _PERSONAL_PREFIXES
        ):
            return RoutingResult(
                MemoryView.PROFILE,
                matched_rule="personal_fact",
                reasoning="preference/first-person fact about the user; profile outlives projects",
            )

        if project_id:
            return RoutingResult(
                MemoryView.PROJECT,
                matched_rule="has_project",
                reasoning=f"anchored to {project_id}",
            )

        if classification.category in _EPISODIC_CATEGORIES:
            return RoutingResult(
                MemoryView.EPISODIC,
                matched_rule="session_event",
                reasoning=f"{classification.category} is a time-bound event",
            )

        if "temporary(-1)" in scoring.applied_modifiers:
            return RoutingResult(
                MemoryView.WORKING,
                matched_rule="transient_context",
                reasoning="explicitly short-lived and not anchored to a project",
            )

        return RoutingResult(
            MemoryView.SEMANTIC,
            matched_rule="general_knowledge",
            reasoning="unanchored durable knowledge (research/concepts/learning)",
        )
