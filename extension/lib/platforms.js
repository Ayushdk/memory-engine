/**
 * Platform registry: URL → platform identity + session id.
 *
 * Pure URL parsing only — DOM selectors live in per-platform adapters.
 * Adding a platform (M5) = one entry here + one adapter file.
 */

const PLATFORMS = [
  {
    id: "chatgpt",
    label: "ChatGPT",
    hosts: ["chatgpt.com", "chat.openai.com"],
    // chatgpt.com/c/<conversation-uuid>
    sessionFromPath: (pathname) => {
      const match = pathname.match(/^\/c\/([A-Za-z0-9-]+)/);
      return match ? `chatgpt-${match[1]}` : null;
    },
  },
];

/**
 * @param {string} urlString
 * @returns {{platform: string, label: string, sessionId: string|null} | null}
 *   null when the URL is not a supported AI platform. sessionId is null on
 *   a supported platform without an open conversation (e.g. the home page).
 */
export function detectPlatform(urlString) {
  let url;
  try {
    url = new URL(urlString);
  } catch {
    return null;
  }
  const entry = PLATFORMS.find((p) => p.hosts.includes(url.hostname));
  if (!entry) return null;
  return {
    platform: entry.id,
    label: entry.label,
    sessionId: entry.sessionFromPath(url.pathname),
  };
}
