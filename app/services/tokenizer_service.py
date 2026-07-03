"""Token estimation for the Context Pack budget.

ponytail: chars/4 — the standard LLM rule of thumb, good enough for a ~1500
token budget. Swap in tiktoken here if per-model precision ever matters.
"""


def estimate_tokens(text: str) -> int:
    return -(-len(text) // 4)  # ceil division; "" → 0
