"""Persistent working memory: the in-memory manager decorated with snapshot +
session bookkeeping. The manager stays pure (deques only); all durability
goes through the repositories. Restores every session buffer on construction,
so an engine restart loses nothing.
"""

from typing import Literal

from app.engine.working_memory.working_memory_manager import WorkingMemoryManager
from app.memory.repositories.session_repository import SessionRepository
from app.memory.repositories.working_memory_repository import WorkingMemoryRepository
from app.models.domain.session import ConversationMessage


class PersistentWorkingMemory:
    def __init__(
        self,
        manager: WorkingMemoryManager,
        working_memory_repository: WorkingMemoryRepository,
        session_repository: SessionRepository,
    ) -> None:
        self._manager = manager
        self._snapshots = working_memory_repository
        self._sessions = session_repository
        self._manager.restore(self._snapshots.load_all())

    def add_message(
        self,
        session_id: str,
        role: Literal["user", "assistant"],
        content: str,
        platform: str = "unknown",
        project_id: str | None = None,
        action: str | None = None,
        matched_rule: str | None = None,
    ) -> ConversationMessage:
        message = self._manager.add_message(
            session_id, role, content, action=action, matched_rule=matched_rule
        )
        self._sessions.touch(session_id, platform, project_id)
        self._snapshots.save_snapshot(session_id, self._manager.get_messages(session_id))
        return message

    def get_messages(
        self, session_id: str, last_n: int | None = None
    ) -> list[ConversationMessage]:
        return self._manager.get_messages(session_id, last_n)

    def clear(self, session_id: str) -> None:
        self._manager.clear(session_id)
        self._snapshots.delete(session_id)
