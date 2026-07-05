// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it } from "vitest";

import { formatLastSync, render, shortenSession } from "../popup/render.js";

const popupHtml = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../popup/popup.html"),
  "utf8",
);

function state(overrides = {}) {
  return {
    engine: { connected: true, version: "0.2.0" },
    settings: { engineUrl: "http://127.0.0.1:8000", apiToken: "", projectId: "", paused: false },
    stats: { ingested: 0, lastSyncAt: null },
    tab: null,
    ...overrides,
  };
}

beforeEach(() => {
  document.documentElement.innerHTML = popupHtml;
});

const text = (id) => document.getElementById(id).textContent;

describe("engine status", () => {
  it("shows connected", () => {
    render(document, state());
    expect(text("engine-label")).toBe("Connected");
    expect(document.getElementById("engine-dot").className).toBe("dot ok");
  });

  it("shows offline", () => {
    render(document, state({ engine: { connected: false, version: null } }));
    expect(text("engine-label")).toBe("Engine offline");
    expect(document.getElementById("engine-dot").className).toBe("dot err");
  });
});

describe("context card", () => {
  it("renders platform and shortened session on a ChatGPT tab", () => {
    const sessionId = "chatgpt-6864f1a2-1b2c-4d5e-8f90-abc123def456";
    render(
      document,
      state({ tab: { platform: "chatgpt", label: "ChatGPT", sessionId } }),
    );
    expect(text("platform")).toBe("ChatGPT");
    expect(text("session")).toBe(shortenSession(sessionId));
    expect(document.getElementById("session").title).toBe(sessionId);
    expect(text("dbg-session")).toBe(sessionId); // debug shows the full id
  });

  it("handles a non-AI tab", () => {
    render(document, state());
    expect(text("platform")).toBe("Not an AI chat");
    expect(text("session")).toBe("—");
  });

  it("fills the project input from settings", () => {
    render(document, state({ settings: { ...state().settings, projectId: "proj_om" } }));
    expect(document.getElementById("project").value).toBe("proj_om");
  });
});

describe("stats and capture", () => {
  it("renders counters and sync age", () => {
    render(document, state({ stats: { ingested: 17, lastSyncAt: null } }));
    expect(text("stat-ingested")).toBe("17");
    expect(text("stat-sync")).toBe("never");
  });

  it("reflects paused state in toggle and subtitle", () => {
    render(document, state({ settings: { ...state().settings, paused: true } }));
    expect(document.getElementById("capture-toggle").checked).toBe(false);
    expect(text("capture-sub")).toContain("Paused");
  });
});

describe("activity indicator", () => {
  const tab = { platform: "chatgpt", label: "ChatGPT", sessionId: "chatgpt-abc" };

  it("shows watching on an active AI tab", () => {
    render(document, state({ tab }));
    expect(text("activity-text")).toBe("Watching this conversation");
    expect(document.getElementById("activity-dot").className).toContain("live");
  });

  it("prioritizes a recent stored memory over watching", () => {
    render(
      document,
      state({
        tab,
        stats: { ingested: 3, lastSyncAt: null, lastMemoryAt: new Date().toISOString() },
      }),
    );
    expect(text("activity-text")).toContain("Memory stored just now");
    expect(document.getElementById("activity-dot").className).toContain("stored");
  });

  it("shows paused above everything else while connected", () => {
    render(document, state({ tab, settings: { ...state().settings, paused: true } }));
    expect(text("activity-text")).toBe("Paused — not remembering");
    expect(document.getElementById("activity-dot").className).toContain("paused");
  });

  it("shows offline when the engine is unreachable", () => {
    render(document, state({ tab, engine: { connected: false, version: null } }));
    expect(text("activity-text")).toContain("Engine offline");
  });

  it("shows idle on a non-AI tab", () => {
    render(document, state());
    expect(text("activity-text")).toContain("Idle");
  });
});

describe("helpers", () => {
  it("shortenSession keeps short ids intact", () => {
    expect(shortenSession("chatgpt-abc")).toBe("chatgpt-abc");
  });

  it("shortenSession abbreviates long ids with head and tail", () => {
    const long = "chatgpt-6864f1a2-1b2c-4d5e-8f90-abc123def456";
    const short = shortenSession(long);
    expect(short.length).toBeLessThan(long.length);
    expect(short).toContain("…");
    expect(long.startsWith(short.split("…")[0])).toBe(true);
    expect(long.endsWith(short.split("…")[1])).toBe(true);
  });

  it("formatLastSync buckets ages", () => {
    const now = Date.parse("2026-07-05T12:00:00Z");
    expect(formatLastSync(null, now)).toBe("never");
    expect(formatLastSync("2026-07-05T11:59:40Z", now)).toBe("just now");
    expect(formatLastSync("2026-07-05T11:45:00Z", now)).toBe("15m ago");
    expect(formatLastSync("2026-07-05T09:00:00Z", now)).toBe("3h ago");
    expect(formatLastSync("2026-07-03T09:00:00Z", now)).toBe("2d ago");
  });
});
