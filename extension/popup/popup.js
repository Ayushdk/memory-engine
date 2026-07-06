/** Popup glue: gather state → render → wire events. Logic lives in render.js. */

import { detectPlatform } from "../lib/platforms.js";
import { render } from "./render.js";

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const platform = tab?.url ? detectPlatform(tab.url) : null;
  return platform ? { ...platform, id: tab.id } : null;
}

async function refresh() {
  const [status, tab] = await Promise.all([
    chrome.runtime.sendMessage({ type: "status" }),
    currentTab(),
  ]);
  render(document, { ...status, tab });
}

document.getElementById("sync").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const hint = document.getElementById("sync-hint");
  const tab = await currentTab();
  if (!tab?.sessionId) return;

  button.disabled = true;
  hint.className = "hint muted";
  hint.textContent = "Syncing…";
  const result = await chrome.runtime.sendMessage({
    type: "sync",
    sessionId: tab.sessionId,
    tabId: tab.id,
  });
  await refresh(); // updates last-sync stat and re-enables the button
  hint.className = result?.ok ? "hint ok" : "hint err";
  hint.textContent = result?.ok
    ? "Context injected — review and send."
    : (result?.error ?? "Sync failed");
});

document.getElementById("settings").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

document.getElementById("capture-toggle").addEventListener("change", async (event) => {
  await chrome.runtime.sendMessage({
    type: "set-settings",
    patch: { paused: !event.target.checked },
  });
  refresh();
});

document.getElementById("project").addEventListener("change", async (event) => {
  await chrome.runtime.sendMessage({
    type: "set-settings",
    patch: { projectId: event.target.value.trim() },
  });
  refresh();
});

refresh();
