"""The V1 rule table — data, not code. Extending the classifier = adding a row.

Evaluation order matters: command rules (delete/merge/update) are checked before
store rules so "we switched to X" never lands as a plain decision, and smalltalk
is checked only against the *whole* message so "Okay, we'll use Postgres" still
stores a decision.
"""

from dataclasses import dataclass
from typing import Literal

from app.models.enums import ClassifierAction, MemoryCategory


@dataclass(frozen=True)
class Rule:
    name: str
    action: ClassifierAction
    category: MemoryCategory | None
    patterns: tuple[str, ...]
    match: Literal["prefix", "contains"] = "contains"


RULES: tuple[Rule, ...] = (
    # User commands about the store itself — prefix-matched so that prose like
    # "we decided to delete the old code" doesn't fire them.
    Rule(
        "delete_command",
        ClassifierAction.DELETE,
        None,
        ("delete ", "forget ", "remove the memory"),
        match="prefix",
    ),
    Rule(
        "merge_command",
        ClassifierAction.MERGE,
        None,
        ("merge ",),
        match="prefix",
    ),
    # Revisions of earlier decisions → UPDATE (supersede, non-destructive)
    Rule(
        "revision",
        ClassifierAction.UPDATE,
        MemoryCategory.DECISION,
        ("we switched", "we changed", "instead of", "switched to", "changed to", "no longer using"),
    ),
    # New facts → STORE
    Rule(
        "decision",
        ClassifierAction.STORE,
        MemoryCategory.DECISION,
        ("i decided", "we decided", "we'll use", "we will use", "let's go with", "going with"),
    ),
    Rule(
        "preference",
        ClassifierAction.STORE,
        MemoryCategory.PREFERENCE,
        ("i prefer", "my favorite", "i like", "i'd rather", "i love", "i hate"),
    ),
    Rule(
        "goal",
        ClassifierAction.STORE,
        MemoryCategory.GOAL,
        ("my goal", "our goal", "the goal is", "we want to", "i want to", "we aim to"),
    ),
    Rule(
        "bug",
        ClassifierAction.STORE,
        MemoryCategory.BUG,
        ("there's a bug", "there is a bug", "found a bug", "doesn't work", "is broken", "crashes"),
    ),
    Rule(
        "task",
        ClassifierAction.STORE,
        MemoryCategory.TASK,
        ("i need to", "we need to", "todo:", "next step is"),
    ),
)

# Matched only when the entire normalized message is one of these.
SMALLTALK: frozenset[str] = frozenset(
    {
        "thanks",
        "thank you",
        "okay",
        "ok",
        "cool",
        "nice",
        "great",
        "hello",
        "hi",
        "hey",
        "good morning",
        "good evening",
        "good night",
        "bye",
        "got it",
        "sounds good",
        "yes",
        "no",
        "sure",
    }
)
