"""Working Memory Manager (architecture.md §4): rolling conversation buffer,
one deque per session, capacity from config, FIFO eviction.

Engine-internal — no FastAPI, no persistence. The SQLite snapshot that lets the
buffer survive restarts lands in Phase 4; importance-weighted eviction is a
V1-optional upgrade over FIFO.
"""

from collections import deque
from typing import Literal

from app.core.config import get_settings
from app.engine.working_memory.session_state import ConversationMessage


class WorkingMemoryManager:
    def __init__(self, capacity: int | None = None) -> None:
        self._capacity = capacity or get_settings().working_memory_capacity
        self._buffers: dict[str, deque[ConversationMessage]] = {}

    def add_message(
        self,
        session_id: str,
        role: Literal["user", "assistant"],
        content: str,
        action: str | None = None,
        matched_rule: str | None = None,
    ) -> ConversationMessage:
        """Append a message; the oldest is evicted once the buffer is full."""
        buffer = self._buffers.setdefault(session_id, deque(maxlen=self._capacity))
        message = ConversationMessage(
            role=role, content=content, action=action, matched_rule=matched_rule
        )
        buffer.append(message)
        return message

    def get_messages(self, session_id: str, last_n: int | None = None) -> list[ConversationMessage]:
        """Messages in arrival order; `last_n` returns only the most recent ones."""
        messages = list(self._buffers.get(session_id, ()))
        return messages[-last_n:] if last_n else messages

    def clear(self, session_id: str) -> None:
        self._buffers.pop(session_id, None)

    def restore(self, snapshots: dict[str, list[ConversationMessage]]) -> None:
        """Rehydrate buffers (e.g. after a restart). Deques re-apply capacity,
        so oversized snapshots are trimmed to the newest messages."""
        for session_id, messages in snapshots.items():
            self._buffers[session_id] = deque(messages, maxlen=self._capacity)
