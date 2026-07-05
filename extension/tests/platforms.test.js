import { describe, expect, it } from "vitest";

import { detectPlatform } from "../lib/platforms.js";

describe("detectPlatform", () => {
  it("detects a ChatGPT conversation and derives the session id", () => {
    expect(detectPlatform("https://chatgpt.com/c/6864f1a2-1b2c-4d5e-8f90-abc123def456")).toEqual({
      platform: "chatgpt",
      label: "ChatGPT",
      sessionId: "chatgpt-6864f1a2-1b2c-4d5e-8f90-abc123def456",
    });
  });

  it("supports the legacy chat.openai.com host", () => {
    expect(detectPlatform("https://chat.openai.com/c/abc-123").sessionId).toBe("chatgpt-abc-123");
  });

  it("returns null sessionId on the platform home page", () => {
    expect(detectPlatform("https://chatgpt.com/")).toEqual({
      platform: "chatgpt",
      label: "ChatGPT",
      sessionId: null,
    });
  });

  it("returns null for unsupported sites and bad URLs", () => {
    expect(detectPlatform("https://example.com/c/123")).toBeNull();
    expect(detectPlatform("not a url")).toBeNull();
    expect(detectPlatform("https://evilchatgpt.com/c/123")).toBeNull(); // exact host match only
  });
});
