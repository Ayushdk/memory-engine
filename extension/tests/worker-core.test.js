import { describe, expect, it } from "vitest";

import { createCore, DEFAULT_STATS } from "../background/worker-core.js";
import { DEFAULT_SETTINGS, loadSettings, saveSettings } from "../lib/settings.js";

/** In-memory chrome.storage.* area fake. */
function fakeArea(initial = {}) {
  const data = { ...initial };
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

function fakeClientFactory({ healthy = true, version = "0.2.0", action = "store" } = {}) {
  const created = [];
  const ingested = [];
  const factory = (options) => {
    created.push(options);
    return {
      async health() {
        if (!healthy) throw new Error("ECONNREFUSED");
        return { status: "ok", version };
      },
      async ingest(payload) {
        if (!healthy) throw new Error("ECONNREFUSED");
        ingested.push(payload);
        return { action, memory_id: "mem_1", synchronization_status: "in_sync" };
      },
    };
  };
  factory.created = created;
  factory.ingested = ingested;
  return factory;
}

describe("settings store", () => {
  it("returns defaults when storage is empty and merges stored values", async () => {
    const area = fakeArea({ projectId: "proj_x" });
    expect(await loadSettings(area)).toEqual({ ...DEFAULT_SETTINGS, projectId: "proj_x" });
  });

  it("saveSettings ignores unknown keys", async () => {
    const area = fakeArea();
    await saveSettings(area, { paused: true, evil: "yes" });
    expect(area.data).toEqual({ paused: true });
  });
});

describe("status message", () => {
  it("reports connected engine with version, settings and default stats", async () => {
    const factory = fakeClientFactory();
    const core = createCore({ local: fakeArea(), session: fakeArea(), clientFactory: factory });

    const status = await core.handle({ type: "status" });
    expect(status.engine).toEqual({ connected: true, version: "0.2.0" });
    expect(status.settings).toEqual(DEFAULT_SETTINGS);
    expect(status.stats).toEqual(DEFAULT_STATS);
  });

  it("builds the client from stored settings (url + token)", async () => {
    const factory = fakeClientFactory();
    const local = fakeArea({ engineUrl: "http://127.0.0.1:8765", apiToken: "s3cret" });
    await createCore({ local, session: fakeArea(), clientFactory: factory }).handle({
      type: "status",
    });
    expect(factory.created[0]).toEqual({ baseUrl: "http://127.0.0.1:8765", token: "s3cret" });
  });

  it("maps empty token to null (auth disabled)", async () => {
    const factory = fakeClientFactory();
    await createCore({ local: fakeArea(), session: fakeArea(), clientFactory: factory }).handle({
      type: "status",
    });
    expect(factory.created[0].token).toBeNull();
  });

  it("reports offline engine without throwing", async () => {
    const factory = fakeClientFactory({ healthy: false });
    const status = await createCore({
      local: fakeArea(),
      session: fakeArea(),
      clientFactory: factory,
    }).handle({ type: "status" });
    expect(status.engine.connected).toBe(false);
    expect(status.engine.reason).toContain("ECONNREFUSED");
  });

  it("returns persisted stats", async () => {
    const session = fakeArea({ ingested: 42, lastSyncAt: "2026-07-05T10:00:00Z" });
    const status = await createCore({
      local: fakeArea(),
      session,
      clientFactory: fakeClientFactory(),
    }).handle({ type: "status" });
    expect(status.stats).toEqual({ ...DEFAULT_STATS, ingested: 42, lastSyncAt: "2026-07-05T10:00:00Z" });
  });
});

describe("set-settings message", () => {
  it("persists the patch", async () => {
    const local = fakeArea();
    const core = createCore({ local, session: fakeArea(), clientFactory: fakeClientFactory() });
    const reply = await core.handle({ type: "set-settings", patch: { projectId: "proj_om" } });
    expect(reply).toEqual({ ok: true, applied: { projectId: "proj_om" } });
    expect(local.data.projectId).toBe("proj_om");
  });
});

describe("test-connection message", () => {
  it("probes the explicit values without saving them", async () => {
    const factory = fakeClientFactory();
    const local = fakeArea();
    const core = createCore({ local, session: fakeArea(), clientFactory: factory });

    const probe = await core.handle({
      type: "test-connection",
      engineUrl: "http://127.0.0.1:9999",
      apiToken: "candidate",
    });
    expect(probe.connected).toBe(true);
    expect(factory.created[0]).toEqual({ baseUrl: "http://127.0.0.1:9999", token: "candidate" });
    expect(local.data).toEqual({}); // nothing persisted
  });
});

describe("unknown messages", () => {
  it("returns a structured error", async () => {
    const core = createCore({
      local: fakeArea(),
      session: fakeArea(),
      clientFactory: fakeClientFactory(),
    });
    expect(await core.handle({ type: "nope" })).toEqual({ error: "unknown message type: nope" });
    expect(await core.handle(undefined)).toEqual({ error: "unknown message type: undefined" });
  });
});

describe("ingest message", () => {
  const payload = {
    sessionId: "chatgpt-abc",
    platform: "chatgpt",
    role: "user",
    content: "We decided to use SQLite.",
    title: "Designing OpenMemory",
  };

  it("forwards to the engine with the configured project and counts it", async () => {
    const factory = fakeClientFactory();
    const local = fakeArea({ projectId: "proj_om" });
    const session = fakeArea();
    const core = createCore({ local, session, clientFactory: factory });

    const reply = await core.handle({ type: "ingest", payload });
    expect(reply).toEqual({ ok: true, action: "store", memoryId: "mem_1" });
    expect(factory.ingested[0]).toMatchObject({ ...payload, projectId: "proj_om" });
    expect(session.data.ingested).toBe(1);
    expect(session.data.lastMemoryAt).toBeTruthy();
  });

  it("does not bump lastMemoryAt for ignored messages", async () => {
    const factory = fakeClientFactory({ action: "ignore" });
    const session = fakeArea();
    const core = createCore({ local: fakeArea(), session, clientFactory: factory });
    await core.handle({ type: "ingest", payload });
    expect(session.data.ingested).toBe(1);
    expect(session.data.lastMemoryAt).toBeUndefined();
  });

  it("refuses while paused — the worker is the single pause authority", async () => {
    const factory = fakeClientFactory();
    const core = createCore({
      local: fakeArea({ paused: true }),
      session: fakeArea(),
      clientFactory: factory,
    });
    expect(await core.handle({ type: "ingest", payload })).toEqual({
      ok: false,
      skipped: "paused",
    });
    expect(factory.ingested).toHaveLength(0);
  });

  it("records engine failures for the activity indicator", async () => {
    const factory = fakeClientFactory({ healthy: false });
    const session = fakeArea();
    const core = createCore({ local: fakeArea(), session, clientFactory: factory });
    const reply = await core.handle({ type: "ingest", payload });
    expect(reply.ok).toBe(false);
    expect(session.data.lastError).toContain("ECONNREFUSED");
    expect(session.data.lastErrorAt).toBeTruthy();
  });

  it("clears the error flag after a successful ingest", async () => {
    const session = fakeArea({ lastError: "old", lastErrorAt: "2026-07-05T09:00:00Z" });
    const core = createCore({
      local: fakeArea(),
      session,
      clientFactory: fakeClientFactory(),
    });
    await core.handle({ type: "ingest", payload });
    expect(session.data.lastError).toBeNull();
  });
});

describe("adapter-broken message", () => {
  it("surfaces the breakage through stats", async () => {
    const session = fakeArea();
    const core = createCore({
      local: fakeArea(),
      session,
      clientFactory: fakeClientFactory(),
    });
    await core.handle({ type: "adapter-broken", platform: "chatgpt" });
    expect(session.data.lastError).toContain("chatgpt page structure changed");
  });
});

describe("sync message", () => {
  const PACK = {
    sections: { profile: ["Prefers TypeScript"] },
  };

  function syncCore({ pack = PACK, tabReply = { ok: true }, session = fakeArea() } = {}) {
    const sentToTab = [];
    const core = createCore({
      local: fakeArea({ projectId: "proj_x" }),
      session,
      clientFactory: () => ({
        async getSyncContext(args) {
          syncCore.lastArgs = args;
          if (pack instanceof Error) throw pack;
          return pack;
        },
      }),
      sendToTab: async (tabId, message) => {
        sentToTab.push({ tabId, message });
        if (tabReply instanceof Error) throw tabReply;
        return tabReply;
      },
    });
    return { core, sentToTab, session };
  }

  const message = { type: "sync", sessionId: "chatgpt-abc", tabId: 42 };

  it("fetches the pack, injects the rendered text, records lastSyncAt", async () => {
    const { core, sentToTab, session } = syncCore();
    expect(await core.handle(message)).toEqual({ ok: true });
    expect(syncCore.lastArgs).toEqual({ sessionId: "chatgpt-abc", projectId: "proj_x" });
    expect(sentToTab).toHaveLength(1);
    expect(sentToTab[0].tabId).toBe(42);
    expect(sentToTab[0].message.type).toBe("inject-context");
    expect(sentToTab[0].message.text).toContain("Prefers TypeScript");
    expect(session.data.lastSyncAt).toBeTruthy();
  });

  it("empty pack → friendly error, nothing sent to the tab", async () => {
    const { core, sentToTab, session } = syncCore({ pack: { sections: {} } });
    expect(await core.handle(message)).toEqual({ ok: false, error: "No memories to sync yet" });
    expect(sentToTab).toHaveLength(0);
    expect(session.data.lastSyncAt).toBeUndefined();
  });

  it("engine failure → ok:false with the error, no lastSyncAt", async () => {
    const { core, session } = syncCore({ pack: new Error("ECONNREFUSED") });
    expect(await core.handle(message)).toEqual({ ok: false, error: "ECONNREFUSED" });
    expect(session.data.lastSyncAt).toBeUndefined();
  });

  it("injection failure reported by the content script is surfaced", async () => {
    const { core, session } = syncCore({
      tabReply: { ok: false, error: "couldn't find the message box on this page" },
    });
    const reply = await core.handle(message);
    expect(reply).toEqual({ ok: false, error: "couldn't find the message box on this page" });
    expect(session.data.lastSyncAt).toBeUndefined();
  });

  it("unreachable content script (no receiver) → reload hint", async () => {
    const { core } = syncCore({ tabReply: new Error("no receiving end") });
    const reply = await core.handle(message);
    expect(reply.ok).toBe(false);
    expect(reply.error).toContain("reloading");
  });
});

describe("status projects", () => {
  it("includes the engine's project list for the popup dropdown", async () => {
    const factory = fakeClientFactory();
    const projects = [{ id: "proj_x", name: "proj_x" }];
    const withProjects = (options) => ({ ...factory(options), listProjects: async () => projects });
    const status = await createCore({
      local: fakeArea(),
      session: fakeArea(),
      clientFactory: withProjects,
    }).handle({ type: "status" });
    expect(status.projects).toEqual(projects);
  });

  it("degrades to an empty list when the engine can't list projects", async () => {
    const status = await createCore({
      local: fakeArea(),
      session: fakeArea(),
      clientFactory: fakeClientFactory(), // fake has no listProjects at all
    }).handle({ type: "status" });
    expect(status.projects).toEqual([]);
  });
});

describe("reset-capture message", () => {
  it("zeroes the counter and clears errors, but keeps lastSyncAt", async () => {
    const session = fakeArea({
      ingested: 42,
      lastMemoryAt: "2026-07-05T10:05:00Z",
      lastError: "boom",
      lastErrorAt: "2026-07-05T10:06:00Z",
      lastSyncAt: "2026-07-05T10:00:00Z",
    });
    const core = createCore({ local: fakeArea(), session, clientFactory: fakeClientFactory() });

    expect(await core.handle({ type: "reset-capture" })).toEqual({ ok: true });

    const status = await core.handle({ type: "status" });
    expect(status.stats).toEqual({ ...DEFAULT_STATS, lastSyncAt: "2026-07-05T10:00:00Z" });
  });

  it("asks the engine to discard the active session before refreshing local stats", async () => {
    const resetSessions = [];
    const session = fakeArea({
      ingested: 3,
      lastMemoryAt: "2026-07-05T10:05:00Z",
      lastSyncAt: "2026-07-05T10:00:00Z",
    });
    const core = createCore({
      local: fakeArea({ engineUrl: "http://engine.local" }),
      session,
      clientFactory: () => ({
        async resetCapture(sessionId) {
          resetSessions.push(sessionId);
        },
      }),
    });

    expect(await core.handle({ type: "reset-capture", sessionId: "chatgpt-abc" })).toEqual({ ok: true });
    expect(resetSessions).toEqual(["chatgpt-abc"]);
    expect(session.data).toMatchObject({ ...DEFAULT_STATS, lastSyncAt: "2026-07-05T10:00:00Z" });
  });

  it("still clears local stats and reports the engine error if backend reset fails", async () => {
    const session = fakeArea({
      ingested: 9,
      lastError: "old",
      lastErrorAt: "2026-07-05T10:06:00Z",
      lastSyncAt: "2026-07-05T10:00:00Z",
    });
    const core = createCore({
      local: fakeArea(),
      session,
      clientFactory: () => ({
        async resetCapture() {
          throw new Error("ECONNREFUSED");
        },
      }),
    });

    expect(await core.handle({ type: "reset-capture", sessionId: "chatgpt-abc" })).toEqual({
      ok: false,
      error: "ECONNREFUSED",
    });
    expect(session.data).toMatchObject({ ...DEFAULT_STATS, lastSyncAt: "2026-07-05T10:00:00Z" });
  });
});
