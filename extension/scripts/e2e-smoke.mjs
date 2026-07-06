/**
 * M2 end-to-end journey smoke — real engine, real extension code.
 *
 * Runs every extension module (adapter → scanner → worker-core → EngineClient
 * → engine → pack renderer → composer injector) against a LIVE engine; only
 * chrome.* and the browser tab are faked (jsdom pages built from the ChatGPT
 * fixtures). The journey mirrors the manual checklist:
 *
 *   1. connect to the running engine
 *   2. open a ChatGPT conversation → messages auto-ingest (exactly once)
 *   3. open a fresh CLAUDE conversation → click Sync Context
 *   4. the pack lands in Claude's composer, typed draft preserved, nothing
 *      submitted — ChatGPT → Claude continuity, the core OpenMemory promise
 *
 * Run from extension/ with the engine on 127.0.0.1:8000:
 *   node scripts/e2e-smoke.mjs        (Windows node when the engine runs on Windows)
 */

import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

import { createCore } from "../background/worker-core.js";
import * as chatgpt from "../content/adapters/chatgpt.js";
import * as claude from "../content/adapters/claude.js";
import { injectIntoComposer } from "../content/injector.js";
import { createScanner, createSeenStore } from "../content/observer.js";
import { detectPlatform } from "../lib/platforms.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = (name) => readFileSync(join(here, "../tests/fixtures", name), "utf8");

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

const step = (label) => console.log(`\n── ${label}`);
const ok = (label) => console.log(`   ✓ ${label}`);

// The "browser": worker-core with fake chrome.storage; sendToTab delivers to
// whichever jsdom "tab" is currently open, exactly like chrome.tabs.sendMessage.
let activeTab = null;
const session = fakeArea();
const core = createCore({
  local: fakeArea(),
  session,
  sendToTab: async (_tabId, message) => activeTab(message),
});

step("1. Connect to the running engine");
const status = await core.handle({ type: "status" });
assert.equal(status.engine.connected, true, "engine must be running on 127.0.0.1:8000");
ok(`engine v${status.engine.version} connected`);

step("2. ChatGPT conversation → messages auto-ingest");
const conversationUrl = `https://chatgpt.com/c/${randomUUID()}`;
const pageA = new JSDOM(fixture("chatgpt-conversation.html"), { url: conversationUrl });
const scanner = createScanner({
  adapter: {
    extractMessages: () => chatgpt.extractMessages(pageA.window.document),
    getTitle: () => chatgpt.getTitle(pageA.window.document),
  },
  detectPlatform,
  sendMessage: (message) => core.handle(message),
  seenStore: createSeenStore(fakeArea()),
});
const first = await scanner.scan({}, conversationUrl);
assert.ok(first.sent >= 2, `expected ingests, got ${JSON.stringify(first)} (stats: ${JSON.stringify(session.data)})`);
ok(`${first.sent} messages ingested (strategy: data-attributes)`);
const again = await scanner.scan({}, conversationUrl);
assert.equal(again.sent, 0, "re-scan must not re-ingest");
ok("re-scan ingested 0 — exactly-once holds against the live engine");

step("3. Fresh CLAUDE conversation → Sync Context (cross-platform handoff)");
const freshUrl = `https://claude.ai/chat/${randomUUID()}`;
const pageB = new JSDOM(fixture("claude-home.html"), { url: freshUrl });
const docB = pageB.window.document;
// injector dispatches DOM events; give it this page's constructors
globalThis.Event = pageB.window.Event;
globalThis.InputEvent = pageB.window.InputEvent;

const composerEl = claude.getComposer(docB).element;
composerEl.textContent = "and what should I do next?"; // a half-typed draft
let submitted = false;
docB.querySelector("form").addEventListener("submit", () => (submitted = true));
activeTab = (message) => injectIntoComposer(claude.getComposer(docB), message.text);

const sync = await core.handle({
  type: "sync",
  sessionId: detectPlatform(freshUrl).sessionId,
  tabId: 1,
});
assert.deepEqual(sync, { ok: true }, `sync failed: ${JSON.stringify(sync)}`);
ok("sync ok — pack fetched, rendered, injected");

step("4. Composer state after injection");
const composerText = composerEl.textContent;
assert.ok(composerText.includes("# Memory context (via OpenMemory)"), "pack header missing");
assert.ok(composerText.endsWith("and what should I do next?"), "typed draft must survive, after the pack");
assert.equal(submitted, false, "must never auto-submit");
assert.ok(session.data.lastSyncAt, "lastSyncAt stat must be recorded");
ok("pack precedes the preserved draft; nothing was submitted; lastSyncAt recorded");
console.log(`\n   Injected pack preview:\n${composerText.split("\n").slice(0, 8).map((l) => `   | ${l}`).join("\n")}\n   | …`);

console.log("\nE2E journey smoke PASSED");
