// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { ADAPTER_INFO, adapterHealth, extractMessages, getComposer, getTitle } from "../content/adapters/chatgpt.js";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

function load(name) {
  document.documentElement.innerHTML = readFileSync(join(FIXTURES, name), "utf8");
  return document;
}

describe("primary strategy: data attributes", () => {
  const result = () => extractMessages(load("chatgpt-conversation.html"));

  it("extracts user and assistant messages in order with DOM ids", () => {
    const { messages, strategy, ok } = result();
    expect(ok).toBe(true);
    expect(strategy).toBe("data-attributes");
    expect(messages.map((m) => [m.id, m.role])).toEqual([
      ["msg-user-001", "user"],
      ["msg-asst-002", "assistant"],
      ["msg-user-003", "user"],
    ]);
  });

  it("takes text from the content node, not the action buttons", () => {
    const { messages } = result();
    expect(messages[0].content).toBe("We decided to use SQLite as the source of truth.");
    expect(messages[1].content).not.toContain("Copy");
  });

  it("keeps assistant markdown text including code blocks", () => {
    const { messages } = result();
    expect(messages[1].content).toContain("SQLite gives you a single durable store,");
    expect(messages[1].content).toContain("reset_db.py");
  });

  it("preserves user line breaks", () => {
    const { messages } = result();
    expect(messages[2].content).toBe("The tricky part is\nthe retrieval endpoint design.");
  });

  it("ignores system/tool turns and empty streaming placeholders", () => {
    const { messages } = result();
    expect(messages.some((m) => m.content.includes("internal system note"))).toBe(false);
    expect(messages.some((m) => m.content === "")).toBe(false);
  });
});

describe("fallback strategy: conversation turns", () => {
  it("extracts when data attributes disappear, inferring roles from structure", () => {
    const { messages, strategy, ok } = extractMessages(load("chatgpt-no-data-attrs.html"));
    expect(ok).toBe(true);
    expect(strategy).toBe("conversation-turns");
    expect(messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(messages[0].content).toBe("Remind me what we picked for storage?");
    expect(messages[1].content).toBe("You chose SQLite with a Chroma index.");
  });
});

describe("failure detection", () => {
  it("fails LOUDLY when a conversation is visible but nothing extracts", () => {
    const { messages, strategy, ok } = extractMessages(load("chatgpt-redesigned.html"));
    expect(messages).toEqual([]);
    expect(strategy).toBeNull();
    expect(ok).toBe(false); // caller must surface "selectors broken"
  });

  it("treats the empty home page as healthy, not broken", () => {
    const { messages, ok } = extractMessages(load("chatgpt-home.html"));
    expect(messages).toEqual([]);
    expect(ok).toBe(true);
  });
});

describe("composer detection", () => {
  it("finds the contenteditable composer", () => {
    const composer = getComposer(load("chatgpt-conversation.html"));
    expect(composer.kind).toBe("contenteditable");
    expect(composer.element.id).toBe("prompt-textarea");
  });

  it("finds a plain textarea composer", () => {
    const composer = getComposer(load("chatgpt-no-data-attrs.html"));
    expect(composer.kind).toBe("textarea");
  });

  it("returns null when no composer exists", () => {
    const composer = getComposer(load("chatgpt-redesigned.html"));
    expect(composer).toBeNull();
  });
});

describe("conversation title", () => {
  it("strips the ChatGPT suffix from the tab title", () => {
    load("chatgpt-conversation.html");
    document.title = "Designing OpenMemory - ChatGPT";
    expect(getTitle(document)).toBe("Designing OpenMemory");
  });

  it("returns null for the bare product title or empty title", () => {
    load("chatgpt-home.html");
    document.title = "ChatGPT";
    expect(getTitle(document)).toBeNull();
    document.title = "";
    expect(getTitle(document)).toBeNull();
  });
});

describe("adapter health", () => {
  it("reports platform, version, strategy and composer on a healthy page", () => {
    expect(adapterHealth(load("chatgpt-conversation.html"))).toEqual({
      ...ADAPTER_INFO,
      ok: true,
      strategy: "data-attributes",
      messageCount: 3,
      composerFound: true,
    });
  });

  it("reports the breakage on a redesigned page", () => {
    const health = adapterHealth(load("chatgpt-redesigned.html"));
    expect(health.ok).toBe(false);
    expect(health.strategy).toBeNull();
    expect(health.composerFound).toBe(false);
  });
});
