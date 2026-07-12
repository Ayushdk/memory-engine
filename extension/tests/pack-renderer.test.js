import { describe, expect, it } from "vitest";

import { renderPack } from "../lib/pack-renderer.js";

function pack(sections = {}) {
  return {
    session_id: "s1",
    generated_at: "2026-07-05T10:00:00Z",
    delta: false,
    token_estimate: 100,
    sections: {
      project_state: null,
      profile: [],
      relevant_memories: [],
      open_questions: [],
      recent_conversation: null,
      ...sections,
    },
  };
}

const FULL = pack({
  project_state: "Backend = FastAPI; storage frozen.",
  profile: ["Prefers diagrams", "Works in Python"],
  relevant_memories: [
    { category: "decision", summary: "We use SQLite as source of truth.", confidence: "high" },
    { category: "decision", summary: "Embeddings stay local.", confidence: "medium" },
    { category: "goal", summary: "Ship V1 by March.", confidence: "high" },
  ],
  open_questions: ["Which cache should we pick?"],
  recent_conversation: {
    platform: "chatgpt",
    minutes_ago: 3,
    messages: ["User: The tricky part is retrieval.", "Assistant: Agreed, ranking needs recency."],
  },
});

describe("full pack", () => {
  const text = renderPack(FULL);

  it("frames the preamble for the receiving LLM", () => {
    expect(text.startsWith("# Memory context (via OpenMemory)")).toBe(true);
    expect(text).toContain("not part of the user's message");
    expect(text.endsWith("_End of memory context. The user's message follows._")).toBe(true);
  });

  it("renders every populated section in order", () => {
    const order = [
      "## Project state",
      "## About the user",
      "## Key memories",
      "## Open questions",
      "## Recent conversation",
    ].map((h) => text.indexOf(h));
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it("groups memories under category headings", () => {
    expect(text).toContain("### Decisions\n- We use SQLite as source of truth.");
    expect(text).toContain("### Goals\n- Ship V1 by March.");
  });

  it("marks non-high confidence, stays silent on high", () => {
    expect(text).toContain("- Embeddings stay local. _(confidence: medium)_");
    expect(text).not.toContain("We use SQLite as source of truth. _(confidence");
  });

  it("labels the recap with platform and age and quotes the dialogue", () => {
    expect(text).toContain("## Recent conversation (on chatgpt, 3 min ago)");
    expect(text).toContain("> User: The tricky part is retrieval.");
    expect(text).toContain("continue from here");
  });
});

describe("partial and empty packs", () => {
  it("omits empty sections entirely", () => {
    const text = renderPack(pack({ profile: ["Only a profile fact"] }));
    expect(text).toContain("## About the user");
    expect(text).not.toContain("## Project state");
    expect(text).not.toContain("## Key memories");
    expect(text).not.toContain("## Open questions");
    expect(text).not.toContain("## Recent conversation");
  });

  it("returns empty string for a contentless pack", () => {
    expect(renderPack(pack())).toBe("");
    expect(renderPack({})).toBe("");
    expect(renderPack(null)).toBe("");
  });

  it("says 'moments ago' for a zero-minute recap", () => {
    const text = renderPack(
      pack({
        recent_conversation: { platform: "chatgpt", minutes_ago: 0, messages: ["User: hi there"] },
      }),
    );
    expect(text).toContain("(on chatgpt, moments ago)");
  });

  it("falls back to the raw category for unknown categories", () => {
    const text = renderPack(
      pack({
        relevant_memories: [{ category: "somethingnew", summary: "X.", confidence: "high" }],
      }),
    );
    expect(text).toContain("### somethingnew");
  });
});

describe("determinism", () => {
  it("same pack renders identically", () => {
    expect(renderPack(FULL)).toBe(renderPack(FULL));
  });
});

describe("workspace section (transfer summary)", () => {
  it("renders '## Current work' right after project state", () => {
    const text = renderPack(
      pack({ project_state: "Building the memory engine.", workspace: "Mid-refactor of the ranking engine." }),
    );
    expect(text).toContain(
      "## Project state\nBuilding the memory engine.\n\n## Current work\nMid-refactor of the ranking engine.",
    );
  });

  it("is omitted when absent", () => {
    const text = renderPack(pack({ project_state: "Building the memory engine." }));
    expect(text).not.toContain("## Current work");
  });
});
