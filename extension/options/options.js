/** Options glue — all engine probing goes through the service worker. */

const urlInput = document.getElementById("engine-url");
const tokenInput = document.getElementById("api-token");
const result = document.getElementById("result");

function show(message, ok) {
  result.hidden = false;
  result.textContent = message;
  result.className = `result ${ok ? "ok" : "err"}`;
}

async function load() {
  const { settings } = await chrome.runtime.sendMessage({ type: "status" });
  urlInput.value = settings.engineUrl;
  tokenInput.value = settings.apiToken;
}

document.getElementById("test").addEventListener("click", async () => {
  show("Testing…", true);
  const probe = await chrome.runtime.sendMessage({
    type: "test-connection",
    engineUrl: urlInput.value.trim(),
    apiToken: tokenInput.value.trim(),
  });
  if (probe.connected) {
    show(`Connected — engine v${probe.version}`, true);
  } else {
    show(`Not reachable: ${probe.reason ?? "unknown error"}`, false);
  }
});

document.getElementById("save").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({
    type: "set-settings",
    patch: { engineUrl: urlInput.value.trim(), apiToken: tokenInput.value.trim() },
  });
  show("Saved.", true);
});

load();
