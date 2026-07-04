from datetime import timedelta

from app.core.config import get_settings
from app.engine.context.session_recap import SessionRecapBuilder
from app.models.domain.session import ConversationMessage, Session
from app.utils.time import utc_now

builder = SessionRecapBuilder()


def msg(content, role="user", action="ignore", matched_rule=None):
    return ConversationMessage(role=role, content=content, action=action, matched_rule=matched_rule)


def session(minutes_ago=5, platform="chatgpt"):
    when = utc_now() - timedelta(minutes=minutes_ago)
    return Session(id="s1", platform=platform, started_at=when, last_activity_at=when)


def test_unstored_dialogue_is_kept_chronologically():
    recap = builder.build(session(), [msg("first point"), msg("second point", role="assistant")])
    assert recap.messages == ["User: first point", "Assistant: second point"]
    assert recap.platform == "chatgpt"
    assert recap.minutes_ago == 5


def test_smalltalk_is_dropped():
    recap = builder.build(
        session(),
        [msg("real discussion"), msg("thanks", matched_rule="smalltalk"), msg("more detail")],
    )
    assert recap.messages == ["User: real discussion", "User: more detail"]


def test_stored_messages_dropped_except_last_two_meaningful():
    recap = builder.build(
        session(),
        [
            msg("we decided to use sqlite", action="store"),  # in long-term memory → dropped
            msg("some unstored nuance"),
            msg("we switched to fastapi", action="update"),  # last-2 meaningful → kept anyway
            msg("what about the port?"),  # last-2 meaningful → kept
        ],
    )
    assert recap.messages == [
        "User: some unstored nuance",
        "User: we switched to fastapi",
        "User: what about the port?",
    ]


def test_last_two_meaningful_skips_trailing_smalltalk():
    recap = builder.build(
        session(),
        [
            msg("we decided on chroma", action="store"),
            msg("key nuance here"),
            msg("ok great", matched_rule="smalltalk"),  # trailing ack is not 'meaningful'
        ],
    )
    # last two MEANINGFUL = stored-decision + nuance → both kept
    assert recap.messages == ["User: we decided on chroma", "User: key nuance here"]


def test_window_limits_to_recent_messages():
    max_messages = get_settings().recap_max_messages
    messages = [msg(f"point {i}") for i in range(max_messages + 3)]
    recap = builder.build(session(), messages)
    assert len(recap.messages) == max_messages
    assert recap.messages[0] == "User: point 3"


def test_asymmetric_truncation():
    recap = builder.build(
        session(),
        [msg("u" * 400, role="user"), msg("a" * 400, role="assistant")],
    )
    user_line, assistant_line = recap.messages
    assert len(user_line) <= len("User: ") + 300
    assert user_line.endswith("…")
    assert len(assistant_line) <= len("Assistant: ") + 200
    assert assistant_line.endswith("…")


def test_budget_trims_oldest_first(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "context_token_budget", 200, raising=True)
    monkeypatch.setattr(settings, "recap_budget_fraction", 0.5, raising=True)  # 100 tokens
    messages = [msg(f"message number {i} " + "x" * 150) for i in range(6)]  # ~40 tokens each

    recap = builder.build(session(), messages)
    assert 0 < len(recap.messages) < 6
    assert recap.messages[-1].startswith("User: message number 5")  # newest survives


def test_all_smalltalk_returns_none():
    recap = builder.build(
        session(), [msg("thanks", matched_rule="smalltalk"), msg("  ", matched_rule=None)]
    )
    assert recap is None


def test_empty_buffer_returns_none():
    assert builder.build(session(), []) is None


def test_multiline_content_is_flattened():
    recap = builder.build(session(), [msg("line one\nline two\n\tindented")])
    assert recap.messages == ["User: line one line two indented"]
