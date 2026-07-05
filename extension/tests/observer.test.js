import { describe, expect, it, vi } from "vitest";

import { createScanner, createSeenStore, keyOf } from "../content/observer.js";
import { detectPlatform } from "../lib/platforms.js";

const URL = "https://chatgpt.com/c/abc-123";

function fakeArea() {
  const data = {};
  return {
    data,
    async get(keys) {
      return Object.fromEntries(keys.filter((k) => k in data).map((k) => [k, data[k]]));
    },
    async set(patch) {
      Object.assign(data, patch);
    },
  };
}

function fakeAdapter(messages, { ok = true, title = "Designing OpenMemory" } = {}) {
  return {
    extractMessages: () => ({ messages, ok, strategy: ok ? "data-attributes" : null }),
    getTitle: () => title,
  };
}

function makeScanner(adapter, { reply = { ok: true, action: "store" }, area = fakeArea() } = {}) {
  const sent = [];
  const sendMessage = vi.fn(async (message) => {
    sent.push(message);
    return typeof reply === "function" ? reply(message) : reply;
  });
  const scanner = createScanner({
    adapter,
    detectPlatform,
    sendMessage,
    seenStore: createSeenStore(area),
  });
  return { scanner, sent, sendMessage, area };
}

const MSGS = [
  { id: "m1", role: "user", content: "We decided to use SQLite." },
  { id: "m2", role: "assistant", content: "Good call." },
];

describe("exactly-once ingestion", () => {
  it("ingests each message once across repeated scans", async () => {
    const { scanner, sent } = makeScanner(fakeAdapter(MSGS));
    expect((await scanner.scan({}, URL)).sent).toBe(2);
    expect((await scanner.scan({}, URL)).sent).toBe(0);
    expect(sent.filter((m) => m.type === "ingest")).toHaveLength(2);
  });

  it("only sends the new message on a later scan", async () => {
    const adapter = fakeAdapter([...MSGS]);
    const { scanner, sent } = makeScanner(adapter);
    await scanner.scan({}, URL);

    adapter.extractMessages = () => ({
      messages: [...MSGS, { id: "m3", role: "user", content: "New thought." }],
      ok: true,
      strategy: "data-attributes",
    });
    const result = await scanner.scan({}, URL);
    expect(result.sent).toBe(1);
    expect(sent.at(-1).payload.content).toBe("New thought.");
  });

  it("streaming/edit updates (same id, new content) do not re-ingest", async () => {
    const adapter = fakeAdapter([{ id: "m1", role: "assistant", content: "partial" }]);
    const { scanner, sent } = makeScanner(adapter);
    await scanner.scan({}, URL);

    adapter.extractMessages = () => ({
      messages: [{ id: "m1", role: "assistant", content: "partial plus the full answer" }],
      ok: true,
      strategy: "data-attributes",
    });
    expect((await scanner.scan({}, URL)).sent).toBe(0);
    expect(sent.filter((m) => m.type === "ingest")).toHaveLength(1);
  });

  it("page refresh does not replay: seen keys persist in storage", async () => {
    const area = fakeArea();
    const first = makeScanner(fakeAdapter(MSGS), { area });
    await first.scanner.scan({}, URL);

    const second = makeScanner(fakeAdapter(MSGS), { area }); // "refreshed page"
    expect((await second.scanner.scan({}, URL)).sent).toBe(0);
  });
});

describe("pause and failure behavior", () => {
  it("paused reply stops the scan without marking seen; resume ingests all", async () => {
    const area = fakeArea();
    let paused = true;
    const { scanner, sent } = makeScanner(fakeAdapter(MSGS), {
      area,
      reply: () => (paused ? { ok: false, skipped: "paused" } : { ok: true, action: "store" }),
    });

    expect((await scanner.scan({}, URL)).sent).toBe(0);
    paused = false;
    expect((await scanner.scan({}, URL)).sent).toBe(2);
    // 1 refused (scan stops at the first paused reply) + 2 accepted on resume
    expect(sent.filter((m) => m.type === "ingest")).toHaveLength(3);
  });

  it("a failed ingest stops mid-scan and retries only the unsent tail", async () => {
    let calls = 0;
    const { scanner } = makeScanner(fakeAdapter(MSGS), {
      reply: () => (++calls === 2 ? { ok: false, error: "boom" } : { ok: true, action: "store" }),
    });
    expect((await scanner.scan({}, URL)).sent).toBe(1); // m1 ok, m2 failed
    expect((await scanner.scan({}, URL)).sent).toBe(1); // only m2 retried
  });
});

describe("adapter failure reporting", () => {
  it("reports a broken adapter exactly once and never ingests", async () => {
    const { scanner, sent } = makeScanner(fakeAdapter([], { ok: false }));
    expect((await scanner.scan({}, URL)).status).toBe("broken");
    await scanner.scan({}, URL);
    expect(sent).toEqual([{ type: "adapter-broken", platform: "chatgpt" }]);
  });
});

describe("scoping and metadata", () => {
  it("does nothing outside a conversation", async () => {
    const { scanner, sent } = makeScanner(fakeAdapter(MSGS));
    expect((await scanner.scan({}, "https://chatgpt.com/")).status).toBe("no-session");
    expect((await scanner.scan({}, "https://example.com/")).status).toBe("no-session");
    expect(sent).toHaveLength(0);
  });

  it("sends session id, platform and title with every message", async () => {
    const { scanner, sent } = makeScanner(fakeAdapter(MSGS));
    await scanner.scan({}, URL);
    expect(sent[0].payload).toMatchObject({
      sessionId: "chatgpt-abc-123",
      platform: "chatgpt",
      title: "Designing OpenMemory",
    });
  });

  it("id-less messages get stable content fingerprints", () => {
    const message = { id: null, role: "user", content: "hello" };
    expect(keyOf(message)).toBe(keyOf({ ...message }));
    expect(keyOf(message)).not.toBe(keyOf({ ...message, content: "hello!" }));
    expect(keyOf(message).startsWith("fp-")).toBe(true);
  });

  it("caps the persisted seen set", async () => {
    const area = fakeArea();
    const store = createSeenStore(area, 3);
    await store.save("s", new Set(["a", "b", "c", "d", "e"]));
    expect(area.data["seen:s"]).toEqual(["c", "d", "e"]);
  });
});
