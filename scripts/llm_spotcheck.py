"""Slice-1 gate: can a small local model clear the extraction quality bar?

Runs a rough extraction prompt over a real conversation excerpt against a
LIVE Ollama and prints the memories the model proposes. This is a viability
probe judged by eye, not a test — the design's biggest untested assumption
(intelligence-layer.md §10 open questions #1 and #5).

Usage (Windows, from repo root, Ollama running with the model pulled):
    python scripts/llm_spotcheck.py [model]     # default: qwen2.5:3b

What to judge in the output:
  - decisions carry alternatives + why rejected (the decision contract)
  - constraints/preferences/ideas are typed sensibly
  - nothing ephemeral is stored (quality over quantity: when in doubt, omit)
"""

import asyncio
import json
import sys
import time

sys.path.insert(0, ".")

from app.engine.llm.ollama_provider import OllamaProvider  # noqa: E402
from app.engine.llm.provider import ProviderError  # noqa: E402

# A condensed real excerpt from OpenMemory's own design sessions — contains a
# decision (with rejected alternative + rationale), a constraint, a
# preference, a deferred idea, and deliberate smalltalk that must NOT be
# stored.
EXCERPT = """\
user: Should we go with Postgres for the memory store? Most examples online use it.
assistant: For a local-first tool, Postgres means running a server. SQLite gives you a
single durable file with zero ops, and since the Chroma vector index can always be
rebuilt from it, SQLite as the source of truth keeps the whole system disposable-index
by design. Postgres only wins if you need concurrent writers, which a single-user
engine never has.
user: Agreed, let's lock in SQLite as the source of truth. One hard rule: no data ever
leaves the machine, no cloud APIs — everything must run locally and free.
assistant: Understood. Local embeddings via MiniLM, embedded Chroma, SQLite. Nothing
leaves the machine.
user: Also, I want us to work in small steps — each step gets tests and my review
before we move to the next one.
assistant: Noted, that will be the workflow.
user: One more thought — a visual dashboard for browsing memories would be great, but
let's not build it now. Maybe after the extension works end to end.
assistant: Makes sense to defer the dashboard until the extension proves the flow.
user: Cool. Anyway, lunch time — talk later!
assistant: Enjoy your lunch!
"""

PROMPT = f"""You extract durable memories from AI-assistant conversations.

Read the conversation below. Return ONLY knowledge that will genuinely improve
future collaboration: decisions (with alternatives considered and why they were
rejected), hard constraints, working preferences, and deliberately deferred
ideas. Every memory must be a self-contained sentence understandable without
the conversation. If in doubt, omit — do not store smalltalk, pleasantries, or
ephemeral chatter. Return an empty list if nothing durable happened.

Conversation:
{EXCERPT}
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "decision",
                            "constraint",
                            "fact",
                            "preference",
                            "insight",
                            "open_question",
                            "idea",
                        ],
                    },
                    "content": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["type", "content"],
            },
        }
    },
    "required": ["memories"],
}


SUMMARY_PROMPT = f"""You maintain working summaries for an AI memory system.

Summarize the conversation below twice:
- "internal": for the engine's own records — preserve every decision,
  constraint, preference, and deferred idea with enough detail to be useful
  months later. A short paragraph is fine.
- "transfer": for handing to another AI assistant mid-work — the most
  compact briefing that lets it continue naturally. 2-3 sentences max.

Use ONLY information present in the conversation. Do not invent names,
dates, technologies, or details.

Conversation:
{EXCERPT}
"""

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"internal": {"type": "string"}, "transfer": {"type": "string"}},
    "required": ["internal", "transfer"],
}


async def probe(provider, label, prompt, schema):
    started = time.monotonic()
    try:
        result = await provider.generate(prompt, schema)
    except ProviderError as exc:
        print(f"\n[{label}] FAILED after {time.monotonic() - started:.1f}s: {exc}")
        return False
    print(f"\n[{label}] ok in {time.monotonic() - started:.1f}s:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return True


async def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:3b"
    provider = OllamaProvider(url="http://127.0.0.1:11434", model=model, timeout=600)

    health = await provider.health()
    print(f"provider health: {health}")
    if not health.available:
        return 1

    # cold-start (load) latency is measured by the first probe; the second
    # runs against a warm model
    ok_summary = await probe(provider, f"{model} summarization", SUMMARY_PROMPT, SUMMARY_SCHEMA)
    ok_extract = await probe(provider, f"{model} extraction", PROMPT, SCHEMA)

    print(
        "\nJudge by eye — extraction: SQLite decision w/ Postgres rejection + "
        "rationale? local-only constraint? small-steps preference? dashboard "
        "idea? NO lunch smalltalk? — summaries: transfer compact, internal "
        "complete? — hallucination: any fact NOT in the excerpt?"
    )
    return 0 if (ok_summary and ok_extract) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
