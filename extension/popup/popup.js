/** Popup glue: gather state → render → wire events. Logic lives in render.js. */

import { detectPlatform } from "../lib/platforms.js";
import { render } from "./render.js";

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.url ? detectPlatform(tab.url) : null;
}

async function refresh() {
  const [status, tab] = await Promise.all([
    chrome.runtime.sendMessage({ type: "status" }),
    currentTab(),
  ]);
  render(document, { ...status, tab });
}

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
