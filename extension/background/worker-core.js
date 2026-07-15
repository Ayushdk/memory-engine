/**
 * Service-worker message handling, extracted from the chrome.* glue so it
 * unit-tests with fakes. The worker is the ONLY component that talks to the
 * engine — popup, options, and content scripts all message through here.
 */

import { EngineClient } from "../lib/engine-client.js";
import { renderPack } from "../lib/pack-renderer.js";
import { loadSettings, saveSettings } from "../lib/settings.js";

export const DEFAULT_STATS = {
  ingested: 0,
  lastSyncAt: null,
  lastMemoryAt: null,
  lastError: null,
  lastErrorAt: null,
};

export function createCore({
  local, // chrome.storage.local (settings)
  session, // chrome.storage.session (volatile stats)
  clientFactory = (options) => new EngineClient(options),
  sendToTab, // (tabId, message) => Promise<reply> — chrome.tabs.sendMessage
}) {
  async function getClient(overrides = {}) {
    const settings = await loadSettings(local);
    return clientFactory({
      baseUrl: overrides.engineUrl ?? settings.engineUrl,
      token: (overrides.apiToken ?? settings.apiToken) || null,
    });
  }

  async function getStats() {
    const stored = await session.get(Object.keys(DEFAULT_STATS));
    return { ...DEFAULT_STATS, ...stored };
  }

  async function probeEngine(overrides = {}) {
    try {
      const health = await (await getClient(overrides)).health();
      return { connected: true, version: health.version ?? null };
    } catch (error) {
      return { connected: false, version: null, reason: error.message };
    }
  }

  const handlers = {
    /** Everything the popup needs to render, in one round trip. */
    async status() {
      const [settings, stats, engine, projects] = await Promise.all([
        loadSettings(local),
        getStats(),
        probeEngine(),
        getClient().then((client) => client.listProjects()).catch(() => []),
      ]);
      return { settings, stats, engine, projects };
    },

    /** Patch settings (popup: project/paused; options: url/token). */
    async "set-settings"({ patch }) {
      const applied = await saveSettings(local, patch ?? {});
      return { ok: true, applied };
    },

    /** Options page "Test connection" — probes explicit values, saves nothing. */
    async "test-connection"({ engineUrl, apiToken }) {
      return probeEngine({ engineUrl, apiToken });
    },

    /**
     * Content-script ingest. Pause is enforced HERE (single authority), so
     * a stale content script can never ingest past the toggle.
     */
    async ingest({ payload }) {
      const settings = await loadSettings(local);
      if (settings.paused) return { ok: false, skipped: "paused" };
      try {
        const result = await (await getClient()).ingest({
          ...payload,
          projectId: settings.projectId || null,
        });
        const patch = { ingested: (await getStats()).ingested + 1, lastError: null };
        if (result.action === "store" || result.action === "update") {
          patch.lastMemoryAt = new Date().toISOString();
        }
        await session.set(patch);
        return { ok: true, action: result.action, memoryId: result.memory_id ?? null };
      } catch (error) {
        await session.set({
          lastError: error.message,
          lastErrorAt: new Date().toISOString(),
        });
        return { ok: false, error: error.message };
      }
    },

    /**
     * Popup Sync button: fetch the Sync Context Pack, render it, and hand it
     * to the content script for composer injection. Never auto-submits — the
     * content side only edits the composer.
     */
    async sync({ sessionId, tabId }) {
      const settings = await loadSettings(local);
      try {
        const pack = await (await getClient()).getSyncContext({
          sessionId,
          projectId: settings.projectId || null,
        });
        const text = renderPack(pack);
        if (!text) return { ok: false, error: "No memories to sync yet" };

        let reply;
        try {
          reply = await sendToTab(tabId, { type: "inject-context", text });
        } catch {
          reply = null; // no content script in the tab (e.g. needs a reload)
        }
        if (!reply?.ok) {
          return { ok: false, error: reply?.error ?? "Couldn't reach the page — try reloading it" };
        }
        await session.set({ lastSyncAt: new Date().toISOString() });
        return { ok: true };
      } catch (error) {
        return { ok: false, error: error.message };
      }
    },

    /**
     * Popup Reset: discard the extension's current capture state — counter
     * back to 0, stale errors cleared. Extension-local only: nothing already
     * synced to the engine (summaries, brain, memories) is touched.
     */
    async "reset-capture"() {
      await session.set({ ...DEFAULT_STATS, lastSyncAt: (await getStats()).lastSyncAt });
      return { ok: true };
    },

    /** Adapter selectors broke: surface it via the activity indicator. */
    async "adapter-broken"({ platform }) {
      await session.set({
        lastError: `${platform} page structure changed — memories paused until the adapter is updated`,
        lastErrorAt: new Date().toISOString(),
      });
      return { ok: true };
    },
  };

  return {
    async handle(message) {
      const handler = handlers[message?.type];
      if (!handler) return { error: `unknown message type: ${message?.type}` };
      try {
        return await handler(message);
      } catch (error) {
        return { error: error.message };
      }
    },
  };
}
