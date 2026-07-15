/** Popup glue: gather state → render → wire events. Logic lives in render.js. */

import { detectPlatform } from "../lib/platforms.js";
import { CREATE_PROJECT_VALUE, render } from "./render.js";

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

document.getElementById("dashboard").addEventListener("click", async () => {
  const status = await chrome.runtime.sendMessage({ type: "status" });
  const base = status?.settings?.engineUrl ?? "http://127.0.0.1:8765";
  const url = new URL("/dashboard", base).toString();
  await chrome.tabs.create({ url });
});

document.getElementById("capture-reset").addEventListener("click", async (event) => {
  if (!confirm("Discard the current unsynced capture and reset the counter? Generated summaries and memories are untouched.")) {
    return;
  }
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const tab = await currentTab();
    await chrome.runtime.sendMessage({ type: "reset-capture", sessionId: tab?.sessionId ?? null });
    await refresh();
  } finally {
    button.disabled = false;
  }
});

document.getElementById("capture-toggle").addEventListener("change", async (event) => {
  await chrome.runtime.sendMessage({
    type: "set-settings",
    patch: { paused: !event.target.checked },
  });
  refresh();
});

document.getElementById("project").addEventListener("change", async (event) => {
  let projectId = event.target.value;
  if (projectId === CREATE_PROJECT_VALUE) {
    const name = prompt("New project name:")?.trim();
    if (!name) {
      await refresh(); // cancelled — snap back to the saved value
      return;
    }
    projectId = name;
  }
  await chrome.runtime.sendMessage({ type: "set-settings", patch: { projectId } });
  await refresh();
});

refresh();
