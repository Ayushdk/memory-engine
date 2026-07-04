"""Per-session conversation state: raw messages, not Memory objects.

ConversationMessage moved to models/domain/session.py so repositories can
persist it without importing engine code (§8 dependency direction); this
re-export keeps existing engine imports working.
"""

from app.models.domain.session import ConversationMessage

__all__ = ["ConversationMessage"]
