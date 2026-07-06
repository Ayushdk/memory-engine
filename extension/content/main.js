/**
 * ChatGPT content entry: wires the scanner to the live page.
 * Debounced MutationObserver — streaming responses mutate continuously, so a
 * scan only fires after the DOM has been quiet for a moment (streams settle
 * before their message is ingested, preventing partial-content memories).
 */

import { detectPlatform } from "../lib/platforms.js";
import * as adapter from "./adapters/chatgpt.js";
import { injectIntoComposer } from "./injector.js";
import { createScanner, createSeenStore } from "./observer.js";

const DEBOUNCE_MS = 1500;

const scanner = createScanner({
  adapter,
  detectPlatform,
  sendMessage: (message) => chrome.runtime.sendMessage(message),
  seenStore: createSeenStore(chrome.storage.local),
});

let timer = null;

function scheduleScan() {
  clearTimeout(timer);
  timer = setTimeout(() => {
    scanner.scan(document, location.href).catch((error) => {
      console.warn("[OpenMemory] scan failed:", error);
    });
  }, DEBOUNCE_MS);
}

// Sync: the worker sends the rendered pack here for composer injection.
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "inject-context") return undefined;
  sendResponse(injectIntoComposer(adapter.getComposer(), message.text));
  return undefined; // response was synchronous
});

new MutationObserver(scheduleScan).observe(document.body, {
  childList: true,
  subtree: true,
  characterData: true,
});

scheduleScan(); // initial scan for an already-loaded conversation
