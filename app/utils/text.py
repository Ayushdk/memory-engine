"""Text helpers."""

import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def summarize(text: str, max_chars: int = 140) -> str | None:
    """Simple summary heuristic: first sentence, whitespace-collapsed, capped.

    Returns None when the result would not be shorter than the original —
    the Context Builder falls back to content, so a non-summary is never
    stored. ponytail: selection, not abstraction; an LLM summarizer replaces
    this call site in M4+.
    """
    collapsed = " ".join(text.split())
    first = _SENTENCE_END.split(collapsed, 1)[0]
    if len(first) > max_chars:
        first = first[: max_chars - 1].rstrip() + "…"
    return first if len(first) < len(collapsed) else None
