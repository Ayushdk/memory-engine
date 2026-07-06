/**
 * Platform-agnostic adapter helpers. Selectors stay in per-platform adapter
 * files — this module only knows how to clean text and classify composers.
 */

/** Normalized visible text of a node: nbsp/trailing-space/blank-run cleanup. */
export function normalizeText(node) {
  return (node.textContent ?? "")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * First usable composer among candidate elements (nulls allowed).
 * @returns {{element: Element, kind: "contenteditable"|"textarea"} | null}
 */
export function composerFrom(candidates) {
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
