"""The V1 scoring rubric — data, not code (mirrors classification_rules.py).

Base score = long-term value of the category; modifiers refine it with
deterministic semantic signals: permanence, dependency, emphasis, transience.
"""

from dataclasses import dataclass

from app.models.enums import MemoryCategory

BASE_SCORES: dict[MemoryCategory, int] = {
    MemoryCategory.DECISION: 9,
    MemoryCategory.ARCHITECTURE: 9,
    MemoryCategory.MILESTONE: 8,
    MemoryCategory.GOAL: 8,
    MemoryCategory.PREFERENCE: 7,
    MemoryCategory.TASK: 7,
    MemoryCategory.RESEARCH: 6,
    MemoryCategory.LEARNING: 6,
    MemoryCategory.BUG: 6,
    MemoryCategory.IDEA: 5,
    MemoryCategory.CODE: 5,
    MemoryCategory.DOCUMENT: 5,
    MemoryCategory.MEETING: 4,
    MemoryCategory.QUESTION: 3,
}


@dataclass(frozen=True)
class Modifier:
    name: str
    delta: int
    patterns: tuple[str, ...]  # matched on word boundaries, case-insensitive


TEXT_MODIFIERS: tuple[Modifier, ...] = (
    Modifier(
        "permanence",
        +1,
        ("always", "never", "permanently", "standard", "default", "from now on"),
    ),
    Modifier(
        "dependency",
        +1,
        ("required", "depends on", "needed for", "prerequisite", "blocks", "blocked by"),
    ),
    Modifier(
        "emphasis",
        +1,
        ("important", "critical", "must", "never forget", "essential", "crucial"),
    ),
    Modifier(
        "temporary",
        -1,
        ("today", "tomorrow", "this week", "later today", "for now", "temporarily"),
    ),
)

# Lookup-style questions ("what is X?") age worse than decision-seeking ones
# ("which store should we pick?"); prefix-matched, QUESTION category only.
INFORMATIONAL_QUESTION_PREFIXES: tuple[str, ...] = (
    "what is",
    "what's",
    "what does",
    "how do",
    "how does",
    "when is",
    "where is",
    "who is",
)
