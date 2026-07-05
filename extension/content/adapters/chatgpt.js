/**
 * ChatGPT DOM adapter — the ONLY file that knows ChatGPT's markup.
 *
 * Defensive by design: multiple extraction strategies tried in order, and an
 * explicit health signal instead of silent misses. If the page clearly shows
 * a conversation but no strategy finds messages, the result says so
 * (`ok: false`) so the caller can surface "selectors broken" instead of
 * quietly remembering nothing.
 */

export const ADAPTER_INFO = { platform: "chatgpt", adapterVersion: "1.0" };

const ROLES = new Set(["user", "assistant"]);

/** Message text: prefer the content node, fall back to the whole element. */
function textOf(element) {
  const contentNode =
    element.querySelector(".markdown") ??
    element.querySelector(".whitespace-pre-wrap") ??
    element;
  return (contentNode.textContent ?? "")
    .replace(/ /g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const STRATEGIES = [
  {
    // Primary: ChatGPT stamps every turn with explicit data attributes.
    name: "data-attributes",
    extract(root) {
      return [...root.querySelectorAll("[data-message-author-role]")].map((el) => ({
        id: el.getAttribute("data-message-id"),
        role: el.getAttribute("data-message-author-role"),
        content: textOf(el),
      }));
    },
  },
  {
    // Fallback: conversation-turn articles; role inferred from structure
    // (assistant turns render markdown, user turns render pre-wrap text).
    name: "conversation-turns",
    extract(root) {
      return [...root.querySelectorAll('article[data-testid^="conversation-turn"]')].map(
        (el, index) => ({
          id: el.getAttribute("data-turn-id") ?? `turn-${index}`,
          role: el.querySelector(".markdown") ? "assistant" : "user",
          content: textOf(el),
        }),
      );
    },
  },
];

/** Signs that a conversation is on screen, independent of message markup. */
function looksLikeConversation(root) {
  return Boolean(
    root.querySelector('#thread, [data-testid^="conversation-turn"], main article'),
  );
}

/**
 * @param {ParentNode} root - document or a container element.
 * @returns {{messages: Array<{id: string|null, role: string, content: string}>,
 *            strategy: string|null, ok: boolean}}
 *   ok=false means: the page looks like a conversation but nothing could be
 *   extracted — selectors are likely broken and the user should know.
 */
export function extractMessages(root = document) {
  for (const strategy of STRATEGIES) {
    const messages = strategy
      .extract(root)
      .filter((m) => ROLES.has(m.role) && m.content.length > 0);
    if (messages.length > 0) {
      return { messages, strategy: strategy.name, ok: true };
    }
  }
  return { messages: [], strategy: null, ok: !looksLikeConversation(root) };
}

/**
 * Conversation title from the document title (ChatGPT sets the tab title to
 * the conversation name). Lightweight metadata only — the session id stays
 * the canonical identifier.
 * @returns {string|null}
 */
export function getTitle(doc = document) {
  const raw = (doc.title ?? "").replace(/\s*[-|–]\s*ChatGPT\s*$/i, "").trim();
  return raw && raw.toLowerCase() !== "chatgpt" ? raw : null;
}

/**
 * One-call adapter health snapshot (popup's future per-platform health row).
 */
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
 * The prompt composer, for Sync injection.
 * @returns {{element: Element, kind: "contenteditable"|"textarea"} | null}
 */
export function getComposer(root = document) {
  const candidates = [
    root.querySelector("#prompt-textarea"),
    root.querySelector('[data-testid="prompt-textarea"]'),
    root.querySelector('form textarea'),
    root.querySelector('form [contenteditable="true"]'),
  ];
  for (const element of candidates) {
    if (!element) continue;
    const kind =
      element.tagName === "TEXTAREA"
        ? "textarea"
        : element.getAttribute("contenteditable") === "true"
          ? "contenteditable"
          : null;
    if (kind) return { element, kind };
  }
  return null;
}
