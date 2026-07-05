// MV3 content scripts are classic scripts; ES modules load via dynamic import.
(async () => {
  const src = chrome.runtime.getURL("content/main.js");
  try {
    await import(src);
  } catch (error) {
    console.error("[OpenMemory] failed to load content module:", error);
  }
})();
