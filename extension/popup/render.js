/**
 * Pure popup rendering: state → DOM updates. No chrome.*, no fetch — glue
 * lives in popup.js, so this renders identically under jsdom in tests.
 *
 * @param {Document} doc
 * @param {object} state
 * @param {{connected: boolean, version: string|null}} state.engine
 * @param {{projectId: string, paused: boolean, engineUrl: string}} state.settings
 * @param {{ingested: number, lastSyncAt: string|null}} state.stats
 * @param {{platform: string, label: string, sessionId: string|null}|null} state.tab
 */
export function render(doc, state) {
  const { engine, settings, stats, tab } = state;
  const $ = (id) => doc.getElementById(id);

  // Engine status pill
  $("engine-dot").className = `dot ${engine.connected ? "ok" : "err"}`;
  $("engine-label").textContent = engine.connected ? "Connected" : "Engine offline";

  // Activity indicator
  const activity = activityState(state);
  $("activity-dot").className = `activity-dot ${activity.kind}`.trim();
  $("activity-text").textContent = activity.text;

  // Sync button — needs a live engine and an open conversation
  $("sync").disabled = !engine.connected || !tab?.sessionId;
  const hint = $("sync-hint");
  hint.className = "hint muted";
  hint.textContent = !engine.connected
    ? "Connect the engine to sync."
    : tab?.sessionId
      ? "Carry this work into any AI assistant."
      : "Open an AI conversation to sync into.";

  // Context card
  $("platform").textContent = tab ? tab.label : "Not an AI chat";
  const session = $("session");
  session.textContent = tab?.sessionId ? shortenSession(tab.sessionId) : "—";
  session.title = tab?.sessionId ?? "";
  if ($("project") !== doc.activeElement) {
    $("project").value = settings.projectId ?? "";
  }

  // Stats
  $("stat-ingested").textContent = String(stats.ingested);
  $("stat-sync").textContent = formatLastSync(stats.lastSyncAt);

  // Workspace controls — need a live engine and a selected project
  const workspaceReady = engine.connected && Boolean(settings.projectId);
  $("ws-archive").disabled = !workspaceReady;
  $("ws-reset").disabled = !workspaceReady;
  if (!$("ws-hint").className.includes("ok") && !$("ws-hint").className.includes("err")) {
    $("ws-hint").textContent = workspaceReady
      ? "Working state updates as you chat."
      : "Connect the engine and pick a project.";
  }

  // Capture toggle
  $("capture-toggle").checked = !settings.paused;
  $("capture-sub").textContent = settings.paused
    ? "Paused — nothing is being remembered"
    : tab
      ? "Remembering this conversation"
      : "Active on supported AI chats";

  $("dashboard").disabled = !engine.connected;

  // Debug
  $("dbg-engine").textContent = settings.engineUrl;
  $("dbg-version").textContent = engine.version ?? "—";
  $("dbg-session").textContent = tab?.sessionId ?? "—";
  $("dbg-project").textContent = settings.projectId || "—";
  $("dbg-ingested").textContent = String(stats.ingested);
  $("dbg-sync").textContent = stats.lastSyncAt ?? "—";
}

/**
 * Live-activity line: reassures the user the extension is actually working.
 * Priority: offline > paused > recent memory > watching > idle.
 */
export function activityState({ engine, settings, stats, tab }, now = Date.now()) {
  if (!engine.connected) return { kind: "", text: "Engine offline — memories on hold" };
  if (settings.paused) return { kind: "paused", text: "Paused — not remembering" };
  if (stats.lastErrorAt && now - Date.parse(stats.lastErrorAt) < 5 * 60000) {
    return { kind: "err", text: stats.lastError ?? "Trouble saving memories" };
  }
  if (stats.lastMemoryAt && now - Date.parse(stats.lastMemoryAt) < 10 * 60000) {
    return { kind: "stored", text: `Memory stored ${formatLastSync(stats.lastMemoryAt, now)}` };
  }
  if (tab) return { kind: "live", text: "Watching this conversation" };
  return { kind: "", text: "Idle — open a supported AI chat" };
}

/** "chatgpt-1f9e…c4d2" — recognizable without eating the popup. */
export function shortenSession(sessionId) {
  if (sessionId.length <= 24) return sessionId;
  return `${sessionId.slice(0, 16)}…${sessionId.slice(-4)}`;
}

/** null → "never"; <1 min → "just now"; then minutes/hours ago. */
export function formatLastSync(isoString, now = Date.now()) {
  if (!isoString) return "never";
  const ageMs = now - Date.parse(isoString);
  if (Number.isNaN(ageMs) || ageMs < 0) return "just now";
  const minutes = Math.floor(ageMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
