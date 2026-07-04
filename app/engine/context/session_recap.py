"""Recent Session Recap — the handoff excerpt for Sync Context.

Pure transformation (mirrors ContextBuilder): buffered messages in, a capped
RecentConversation out. Selection is the complement of long-term memory:
messages that were STOREd/UPDATEd are already in the pack's memory sections
and smalltalk carries no momentum, so what remains is the conversational
tissue long-term memory did NOT capture — except the last two meaningful
messages, which are always kept ("what were we literally just saying").

ponytail: concise = selection + truncation, not abstraction; an LLM
summarizer strategy can replace this module in M4+ behind the same call.
"""

from app.core.config import get_settings
from app.models.domain.context_pack import RecentConversation
from app.models.domain.session import ConversationMessage, Session
from app.services.tokenizer_service import estimate_tokens
from app.utils.time import utc_now

_STORED_ACTIONS = {"store", "update"}
_TRUNCATE = {"user": 300, "assistant": 200}  # intent lives in user turns


def _meaningful(message: ConversationMessage) -> bool:
    return message.matched_rule != "smalltalk" and bool(message.content.strip())


def _render(message: ConversationMessage) -> str:
    limit = _TRUNCATE[message.role]
    content = " ".join(message.content.split())  # collapse whitespace/newlines
    if len(content) > limit:
        content = content[: limit - 1].rstrip() + "…"
    return f"{'User' if message.role == 'user' else 'Assistant'}: {content}"


class SessionRecapBuilder:
    def build(
        self, session: Session, messages: list[ConversationMessage]
    ) -> RecentConversation | None:
        settings = get_settings()
        tail = messages[-settings.recap_max_messages :]

        meaningful = [m for m in tail if _meaningful(m)]
        always_keep = {id(m) for m in meaningful[-2:]}  # last two meaningful, even if stored
        selected = [
            m
            for m in meaningful
            if id(m) in always_keep or (m.action or "") not in _STORED_ACTIONS
        ]
        if not selected:
            return None

        # Own sub-budget, a fraction of the total pack budget; oldest out first —
        # in a recap, newest matters most (mirror of the relevant-memories rule).
        budget = int(settings.context_token_budget * settings.recap_budget_fraction)
        rendered = [_render(m) for m in selected]
        while len(rendered) > 1 and sum(estimate_tokens(r) for r in rendered) > budget:
            rendered.pop(0)

        minutes_ago = max(0, int((utc_now() - session.last_activity_at).total_seconds() // 60))
        return RecentConversation(
            platform=session.platform, minutes_ago=minutes_ago, messages=rendered
        )
