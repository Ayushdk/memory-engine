/**
 * Claude DOM adapter — the ONLY file that knows claude.ai's markup.
 *
 * Same defensive contract as the ChatGPT adapter: multiple extraction
 * strategies tried in order, explicit `ok: false` when a conversation is
 * visibly on screen but nothing extracts.
 *
 * Claude exposes no stable per-message DOM ids, so `id` is always null and
 * the observer dedupes on content fingerprints instead; the 1.5s DOM-quiet
 * debounce keeps streaming partials from being fingerprinted mid-flight.
 */

import { composerFrom, normalizeText } from "./shared.js";

export const ADAPTER_INFO = { platform: "claude", adapterVersion: "1.0" };

const STRATEGIES = [
  {
    // Primary: role-bearing font classes on every message body.
    name: "font-classes",
    extract(root) {
      return [...root.querySelectorAll(".font-user-message, .font-claude-message")].map(
        (el) => ({
          id: null,
          role: el.classList.contains("font-user-message") ? "user" : "assistant",
          content: normalizeText(el),
        }),
      );
    },
  },
  {
    // Fallback: render-count turn wrappers; role from the user-message testid.
    name: "turn-wrappers",
    extract(root) {
      return [...root.querySelectorAll("[data-test-render-count]")].map((el) => ({
        id: null,
        role: el.querySelector('[data-testid="user-message"]') ? "user" : "assistant",
        content: normalizeText(el),
      }));
    },
  },
];

/** Signs that a conversation is on screen, independent of message markup. */
function looksLikeConversation(root) {
  return Boolean(
    root.querySelector(
      '[data-test-render-count], .font-claude-message, [data-testid="user-message"]',
    ),
  );
}

/**
 * @param {ParentNode} root - document or a container element.
 * @returns {{messages: Array<{id: null, role: string, content: string}>,
 *            strategy: string|null, ok: boolean}}
 */
export function extractMessages(root = document) {
  for (const strategy of STRATEGIES) {
    const messages = strategy.extract(root).filter((m) => m.content.length > 0);
    if (messages.length > 0) {
      return { messages, strategy: strategy.name, ok: true };
    }
  }
  return { messages: [], strategy: null, ok: !looksLikeConversation(root) };
}

/**
 * Conversation title from the tab title ("<name> - Claude"). Lightweight
 * metadata only — the session id stays the canonical identifier.
 * @returns {string|null}
 */
export function getTitle(doc = document) {
  const raw = (doc.title ?? "").replace(/\s*[-|–]\s*Claude\s*$/i, "").trim();
  return raw && raw.toLowerCase() !== "claude" ? raw : null;
}

/** One-call adapter health snapshot. */
export function adapterHealth(root = document) {
  const { ok, strategy, messages } = extractMessages(root);
  return {
    ...ADAPTER_INFO,
    ok,
    strategy,
    messageCount: messages.length,
    composerFound: getComposer(root) !== null,
  };
}

/**
 * The prompt composer (ProseMirror contenteditable), for Sync injection.
 * @returns {{element: Element, kind: "contenteditable"|"textarea"} | null}
 */
export function getComposer(root = document) {
  return composerFrom([
    root.querySelector('[data-testid="chat-input"]'),
    root.querySelector('[aria-label*="prompt to Claude" i]'),
    root.querySelector('div.ProseMirror[contenteditable="true"]'),
    root.querySelector("form textarea"),
    root.querySelector('form [contenteditable="true"]'),
  ]);
}
