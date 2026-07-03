"""Closed vocabularies shared by every layer (architecture.md §3)."""

from enum import StrEnum


class MemoryCategory(StrEnum):
    """What kind of information a memory holds."""

    DECISION = "decision"
    PREFERENCE = "preference"
    GOAL = "goal"
    QUESTION = "question"
    IDEA = "idea"
    MEETING = "meeting"
    BUG = "bug"
    ARCHITECTURE = "architecture"
    RESEARCH = "research"
    TASK = "task"
    MILESTONE = "milestone"
    LEARNING = "learning"
    CODE = "code"
    DOCUMENT = "document"


class MemoryView(StrEnum):
    """Logical view a memory belongs to. Views are filters over the unified
    store, never separate tables (locked decision #2)."""

    WORKING = "working"
    PROFILE = "profile"
    PROJECT = "project"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class ClassifierAction(StrEnum):
    """What the classifier decides to do with an incoming message."""

    IGNORE = "ignore"
    STORE = "store"
    UPDATE = "update"
    MERGE = "merge"
    DELETE = "delete"


class Confidence(StrEnum):
    """How sure the system is about a memory. V1: high for explicit
    statements, medium for inferences (locked decision #7)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MemoryStatus(StrEnum):
    """Lifecycle state. Updates are non-destructive: a new memory
    supersedes the old one rather than overwriting it."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    MERGED = "merged"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
