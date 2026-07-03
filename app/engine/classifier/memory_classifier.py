"""Memory Classifier — strategy interface + the V1 rules implementation.

Strategy-swap contract (architecture.md §4): the pipeline calls
`classify(message, working_memory) -> ClassificationResult` and never knows
which strategy runs. V2 drops in Ollama/Gemini/local-model classifiers behind
the same Protocol without touching the orchestrator.
"""

import string
from dataclasses import dataclass
from typing import Protocol, Sequence

from app.core.config import get_settings
from app.engine.classifier.classification_rules import RULES, SMALLTALK
from app.engine.working_memory.session_state import ConversationMessage
from app.models.enums import ClassifierAction, MemoryCategory


@dataclass(frozen=True)
class ClassificationResult:
    action: ClassifierAction
    category: MemoryCategory | None = None
    matched_rule: str | None = None
    reason: str | None = None


class MemoryClassifier(Protocol):
    def classify(
        self, message: str, working_memory: Sequence[ConversationMessage] = ()
    ) -> ClassificationResult: ...


class RuleClassifier:
    """Deterministic table-driven classifier. Offline, free, testable.

    working_memory is accepted per the strategy contract but unused by rules;
    LLM strategies will use it as conversation context.
    """

    def classify(
        self, message: str, working_memory: Sequence[ConversationMessage] = ()
    ) -> ClassificationResult:
        normalized = message.strip().lower()

        for rule in RULES:
            hit = (
                normalized.startswith(rule.patterns)
                if rule.match == "prefix"
                else any(p in normalized for p in rule.patterns)
            )
            if hit:
                return ClassificationResult(
                    action=rule.action,
                    category=rule.category,
                    matched_rule=rule.name,
                    reason=f"matched rule '{rule.name}'",
                )

        if normalized.rstrip(string.punctuation + " ") in SMALLTALK:
            return ClassificationResult(
                action=ClassifierAction.IGNORE, matched_rule="smalltalk", reason="smalltalk"
            )

        if normalized.endswith("?"):
            return ClassificationResult(
                action=ClassifierAction.STORE,
                category=MemoryCategory.QUESTION,
                matched_rule="question",
                reason="ends with question mark",
            )

        # Conservative V1 default: unmatched conversation is not stored.
        return ClassificationResult(action=ClassifierAction.IGNORE, reason="no_matching_rule")


def create_classifier(strategy: str | None = None) -> MemoryClassifier:
    """Config-selected strategy (`rules | ollama | gemini`); V1 ships rules only."""
    strategy = strategy or get_settings().classifier_strategy
    if strategy == "rules":
        return RuleClassifier()
    raise NotImplementedError(f"classifier strategy '{strategy}' is not implemented in V1")
