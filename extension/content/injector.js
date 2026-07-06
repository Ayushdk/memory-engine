/**
 * Composer injection — puts the rendered Context Pack into the page's prompt
 * box. Guarantees: never submits; any text the user already typed is
 * preserved AFTER the pack (the pack ends with "the user's message follows",
 * so context must precede it); the cursor lands at the very end so the user
 * can keep typing naturally.
 */

/**
 * @param {{element: Element, kind: "contenteditable"|"textarea"}|null} composer
 * @param {string} text - rendered pack; must be non-empty.
 * @returns {{ok: true} | {ok: false, error: string}}
 */
export function injectIntoComposer(composer, text) {
  if (!text) return { ok: false, error: "nothing to inject" };
  if (!composer?.element) {
    return { ok: false, error: "couldn't find the message box on this page" };
  }
  try {
    return composer.kind === "textarea"
      ? injectTextarea(composer.element, text)
      : injectContentEditable(composer.element, text);
  } catch (error) {
    return { ok: false, error: `injection failed: ${error.message}` };
  }
}

function injectTextarea(element, text) {
  const existing = element.value;
  element.value = existing ? `${text}\n\n${existing}` : text;
  // React/controlled inputs only see the change through an input event.
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.focus();
  element.setSelectionRange(element.value.length, element.value.length);
  return { ok: true };
}

function injectContentEditable(element, text) {
  const doc = element.ownerDocument;
  const payload = (element.textContent ?? "").trim() ? `${text}\n\n` : text;

  element.focus();
  const selection = doc.getSelection();
  const start = doc.createRange();
  start.setStart(element, 0);
  start.collapse(true);
  selection.removeAllRanges();
  selection.addRange(start);

  // execCommand goes through the editor's own input pipeline (ProseMirror
  // et al.), so state stays consistent. Fallback: raw DOM insert + the same
  // input event the editor listens for.
  const inserted = doc.execCommand?.("insertText", false, payload);
  if (!inserted) {
    element.insertBefore(doc.createTextNode(payload), element.firstChild);
    element.dispatchEvent(
      new InputEvent("input", { bubbles: true, inputType: "insertText", data: payload }),
    );
  }

  selection.selectAllChildren(element);
  selection.collapseToEnd();
  return { ok: true };
}
