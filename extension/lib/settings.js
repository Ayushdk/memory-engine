/**
 * Extension settings, backed by an injectable chrome.storage area so the
 * logic tests in plain Node with a fake area.
 */

export const DEFAULT_SETTINGS = {
  engineUrl: "http://127.0.0.1:8000",
  apiToken: "",
  projectId: "",
  paused: false,
};

/** @param {{get: Function}} area - chrome.storage.local or a test fake. */
export async function loadSettings(area) {
  const stored = await area.get(Object.keys(DEFAULT_SETTINGS));
  return { ...DEFAULT_SETTINGS, ...stored };
}

/** @param {{set: Function}} area @param {object} patch - partial settings. */
export async function saveSettings(area, patch) {
  const known = Object.fromEntries(
    Object.entries(patch).filter(([key]) => key in DEFAULT_SETTINGS),
  );
  await area.set(known);
  return known;
}
