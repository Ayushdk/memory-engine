/** Thin chrome glue around worker-core (which holds all the logic). */

import { createCore } from "./worker-core.js";

const core = createCore({
  local: chrome.storage.local,
  session: chrome.storage.session,
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  core.handle(message).then(sendResponse);
  return true; // keep the channel open for the async response
});
