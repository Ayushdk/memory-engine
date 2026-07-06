// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";

import { injectIntoComposer } from "../content/injector.js";

const PACK = "# Memory context\n- We use SQLite.";

function textarea(value = "") {
  const el = document.createElement("textarea");
  el.value = value;
  document.body.append(el);
  return { element: el, kind: "textarea" };
}

function contentEditable(text = "") {
  const el = document.createElement("div");
  el.setAttribute("contenteditable", "true");
  if (text) el.textContent = text;
  document.body.append(el);
  return { element: el, kind: "contenteditable" };
}

describe("guard rails", () => {
  it("fails clearly when the composer is missing", () => {
    expect(injectIntoComposer(null, PACK)).toEqual({
      ok: false,
      error: "couldn't find the message box on this page",
    });
  });

  it("refuses to inject empty text", () => {
    expect(injectIntoComposer(textarea(), "").ok).toBe(false);
  });

  it("returns ok:false instead of throwing on DOM errors", () => {
    const composer = textarea();
    Object.defineProperty(composer.element, "value", {
      set() {
        throw new Error("boom");
      },
    });
    const result = injectIntoComposer(composer, PACK);
    expect(result.ok).toBe(false);
    expect(result.error).toContain("boom");
  });
});

describe("textarea composer", () => {
  it("injects the pack and fires an input event (no submit)", () => {
    const composer = textarea();
    const onInput = vi.fn();
    composer.element.addEventListener("input", onInput);
    const onSubmit = vi.fn();
    composer.element.closest("body").addEventListener("submit", onSubmit);

    expect(injectIntoComposer(composer, PACK)).toEqual({ ok: true });
    expect(composer.element.value).toBe(PACK);
    expect(onInput).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("preserves already-typed text AFTER the pack, cursor at the end", () => {
    const composer = textarea("my half-written question");
    injectIntoComposer(composer, PACK);
    expect(composer.element.value).toBe(`${PACK}\n\nmy half-written question`);
    expect(composer.element.selectionStart).toBe(composer.element.value.length);
    expect(composer.element.selectionEnd).toBe(composer.element.value.length);
  });
});

describe("contenteditable composer", () => {
  it("injects via DOM fallback and fires an input event", () => {
    const composer = contentEditable();
    const onInput = vi.fn();
    composer.element.addEventListener("input", onInput);

    expect(injectIntoComposer(composer, PACK)).toEqual({ ok: true });
    expect(composer.element.textContent).toBe(PACK);
    expect(onInput).toHaveBeenCalledOnce();
  });

  it("preserves already-typed text after the pack", () => {
    const composer = contentEditable("my half-written question");
    injectIntoComposer(composer, PACK);
    expect(composer.element.textContent).toBe(`${PACK}\n\nmy half-written question`);
  });

  it("uses execCommand when the editor supports it", () => {
    const composer = contentEditable();
    document.execCommand = vi.fn(() => true);
    try {
      injectIntoComposer(composer, PACK);
      expect(document.execCommand).toHaveBeenCalledWith("insertText", false, PACK);
      expect(composer.element.textContent).toBe(""); // real editor would apply it
    } finally {
      delete document.execCommand;
    }
  });
});
