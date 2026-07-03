"""Importance Scorer — strategy interface + the V1 rubric implementation.

Same strategy-swap contract as the classifier (architecture.md §4): the
pipeline calls `score(classification, message, project_id)` and never knows
whether rules or an LLM produced the number.
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import get_settings
from app.engine.classifier.memory_classifier import ClassificationResult
from app.engine.scorer.scoring_policy import (
    BASE_SCORES,
    INFORMATIONAL_QUESTION_PREFIXES,
    TEXT_MODIFIERS,
)
from app.models.enums import MemoryCategory


@dataclass(frozen=True)
class ScoringResult:
    importance: int  # 0-10, clamped
    base_score: int
    applied_modifiers: list[str] = field(default_factory=list)
    reasoning: str | None = None


class ImportanceScorer(Protocol):
    def score(
        self,
        classification: ClassificationResult,
        message: str,
        project_id: str | None = None,
    ) -> ScoringResult: ...


class RuleImportanceScorer:
    """Deterministic rubric: category base score ± semantic modifiers."""

    def score(
        self,
        classification: ClassificationResult,
        message: str,
        project_id: str | None = None,
    ) -> ScoringResult:
        base = BASE_SCORES.get(classification.category, 0) if classification.category else 0
        normalized = message.strip().lower()
        applied: list[str] = []
        delta = 0

        if project_id:
            applied.append("has_project(+1)")
            delta += 1

        for modifier in TEXT_MODIFIERS:
            if any(re.search(rf"\b{re.escape(p)}\b", normalized) for p in modifier.patterns):
                applied.append(f"{modifier.name}({modifier.delta:+d})")
                delta += modifier.delta

        if classification.category is MemoryCategory.QUESTION and normalized.startswith(
            INFORMATIONAL_QUESTION_PREFIXES
        ):
            applied.append("informational_question(-1)")
            delta -= 1

        importance = max(0, min(10, base + delta))
        return ScoringResult(
            importance=importance,
            base_score=base,
            applied_modifiers=applied,
            reasoning=f"base {base} ({classification.category or 'no category'}) "
            f"{'+ ' + ', '.join(applied) if applied else 'with no modifiers'}",
        )


def create_scorer(strategy: str | None = None) -> ImportanceScorer:
    """Config-selected strategy (`rules | ollama | gemini`); V1 ships rules only."""
    strategy = strategy or get_settings().scorer_strategy
    if strategy == "rules":
        return RuleImportanceScorer()
    raise NotImplementedError(f"scorer strategy '{strategy}' is not implemented in V1")
