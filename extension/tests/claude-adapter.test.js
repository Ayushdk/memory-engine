// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { ADAPTER_INFO, adapterHealth, extractMessages, getComposer, getTitle } from "../content/adapters/claude.js";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

function load(name) {
  document.documentElement.innerHTML = readFileSync(join(FIXTURES, name), "utf8");
  return document;
}

describe("primary strategy: font classes", () => {
  const result = () => extractMessages(load("claude-conversation.html"));

  it("extracts user and assistant messages in order (ids are null)", () => {
    const { messages, strategy, ok } = result();
    expect(ok).toBe(true);
    expect(strategy).toBe("font-classes");
    expect(messages.map((m) => [m.id, m.role])).toEqual([
      [null, "user"],
      [null, "assistant"],
      [null, "user"],
    ]);
  });

  it("takes text from the message body, not the action buttons", () => {
    const { messages } = result();
    expect(messages[0].content).toBe("We decided to use SQLite as the source of truth.");
    expect(messages[1].content).not.toContain("Copy");
    expect(messages[1].content).not.toContain("Retry");
  });

  it("keeps assistant text including code blocks", () => {
    const { messages } = result();
    expect(messages[1].content).toContain("SQLite gives you a single durable store,");
    expect(messages[1].content).toContain("reset_db.py");
  });

  it("preserves user line breaks", () => {
    const { messages } = result();
    expect(messages[2].content).toBe("The tricky part is\nthe retrieval endpoint design.");
  });

  it("ignores empty streaming placeholders", () => {
    const { messages } = result();
    expect(messages).toHaveLength(3);
    expect(messages.some((m) => m.content === "")).toBe(false);
  });
});

describe("fallback strategy: turn wrappers", () => {
  it("extracts when font classes disappear, inferring roles from the user testid", () => {
    const { messages, strategy, ok } = extractMessages(load("claude-no-font-classes.html"));
    expect(ok).toBe(true);
    expect(strategy).toBe("turn-wrappers");
    expect(messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(messages[0].content).toBe("Remind me what we picked for storage?");
    expect(messages[1].content).toBe("You chose SQLite with a Chroma index.");
  });
});

describe("failure detection", () => {
  it("fails LOUDLY when a conversation is visible but nothing extracts", () => {
    const { messages, strategy, ok } = extractMessages(load("claude-redesigned.html"));
    expect(messages).toEqual([]);
    expect(strategy).toBeNull();
    expect(ok).toBe(false); // caller must surface "selectors broken"
  });

  it("treats the empty home page as healthy, not broken", () => {
    const { messages, ok } = extractMessages(load("claude-home.html"));
    expect(messages).toEqual([]);
    expect(ok).toBe(true);
  });
});

describe("composer detection", () => {
  it("finds the ProseMirror contenteditable composer", () => {
    const composer = getComposer(load("claude-conversation.html"));
    expect(composer.kind).toBe("contenteditable");
    expect(composer.element.getAttribute("data-testid")).toBe("chat-input");
  });

  it("finds a plain textarea composer", () => {
    const composer = getComposer(load("claude-no-font-classes.html"));
    expect(composer.kind).toBe("textarea");
  });

  it("returns null when no composer exists", () => {
    expect(getComposer(load("claude-redesigned.html"))).toBeNull();
  });
});

describe("conversation title", () => {
  it("strips the Claude suffix from the tab title", () => {
    load("claude-conversation.html");
    document.title = "Designing OpenMemory - Claude";
    expect(getTitle(document)).toBe("Designing OpenMemory");
  });

  it("returns null for the bare product title or empty title", () => {
    load("claude-home.html");
    document.title = "Claude";
    expect(getTitle(document)).toBeNull();
    document.title = "";
    expect(getTitle(document)).toBeNull();
  });
});

describe("adapter health", () => {
  it("reports platform, version, strategy and composer on a healthy page", () => {
    expect(adapterHealth(load("claude-conversation.html"))).toEqual({
      ...ADAPTER_INFO,
      ok: true,
      strategy: "font-classes",
      messageCount: 3,
      composerFound: true,
    });
  });

  it("reports the breakage on a redesigned page", () => {
    const health = adapterHealth(load("claude-redesigned.html"));
    expect(health.ok).toBe(false);
    expect(health.strategy).toBeNull();
    expect(health.composerFound).toBe(false);
  });
});
