/**
 * Platform-agnostic ingest scanner. Reliability contract:
 *
 * - exactly-once: seen-keys persisted per session in chrome.storage.local,
 *   so refreshes and browser restarts never replay a conversation
 * - streaming/edit safe: keyed by the platform's stable message id (same id,
 *   new content → no re-ingest); callers debounce so streams settle first
 * - pause safe: a paused reply stops the scan WITHOUT marking messages seen —
 *   nothing is lost, everything ingests on resume
 * - failure safe: an error reply stops the scan without marking seen (retry
 *   on next scan) and the worker records it for the activity indicator
 * - selector safe: a broken adapter (ok=false) is reported once per page
 */

/** Stable key: DOM message id, else a content fingerprint (djb2). */
export function keyOf(message) {
  if (message.id) return message.id;
  let hash = 5381;
  const text = `${message.role}:${message.content}`;
  for (let i = 0; i < text.length; i++) {
    hash = ((hash << 5) + hash + text.charCodeAt(i)) >>> 0;
  }
  return `fp-${hash.toString(36)}`;
}

/** Per-session ingested-key store over chrome.storage.local (capped FIFO). */
export function createSeenStore(area, cap = 500) {
  const storageKey = (sessionId) => `seen:${sessionId}`;
  return {
    async load(sessionId) {
      const stored = await area.get([storageKey(sessionId)]);
      return new Set(stored[storageKey(sessionId)] ?? []);
    },
    async save(sessionId, seen) {
      await area.set({ [storageKey(sessionId)]: [...seen].slice(-cap) });
    },
  };
}

export function createScanner({ adapter, detectPlatform, sendMessage, seenStore }) {
  let reportedBroken = false;

  return {
    /**
     * @param {ParentNode} root - DOM to scan.
     * @param {string} url - current page URL.
     * @returns {{status: string, sent?: number}}
     */
    async scan(root, url) {
      const detected = detectPlatform(url);
      if (!detected?.sessionId) return { status: "no-session" };

      const { messages, ok } = adapter.extractMessages(root);
      if (!ok) {
        if (!reportedBroken) {
          reportedBroken = true;
          await sendMessage({ type: "adapter-broken", platform: detected.platform });
        }
        return { status: "broken" };
      }

      const seen = await seenStore.load(detected.sessionId);
      const fresh = messages.filter((m) => !seen.has(keyOf(m)));
      if (fresh.length === 0) return { status: "ok", sent: 0 };

      const title = adapter.getTitle?.(root.ownerDocument ?? root) ?? null;
      let sent = 0;
      try {
        for (const message of fresh) {
          console.debug(
            `[OpenMemory] captured ${message.role} message, len=${message.content.length}`,
          );
          const reply = await sendMessage({
            type: "ingest",
            payload: {
              sessionId: detected.sessionId,
              platform: detected.platform,
              role: message.role,
              content: message.content,
              title,
            },
          });
          if (!reply?.ok) break; // paused or failing: stop, keep unseen, retry later
          seen.add(keyOf(message));
          sent++;
        }
      } finally {
        if (sent > 0) await seenStore.save(detected.sessionId, seen);
      }
      return { status: "ok", sent };
    },
  };
}
