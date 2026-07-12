import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { loadConfig, saveConfig, api, ApiError } from "./api";

describe("config", () => {
  beforeEach(() => localStorage.clear());

  it("defaults to /api/v1 with no token", () => {
    expect(loadConfig()).toEqual({ baseUrl: "/api/v1", token: "" });
  });

  it("round-trips through localStorage", () => {
    saveConfig({ baseUrl: "http://x", token: "secret" });
    expect(loadConfig()).toEqual({ baseUrl: "http://x", token: "secret" });
  });
});

describe("request", () => {
  beforeEach(() => {
    localStorage.clear();
    saveConfig({ baseUrl: "http://engine", token: "tok" });
  });
  afterEach(() => vi.restoreAllMocks());

  it("attaches bearer token and base url", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    await api.health();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://engine/health");
    expect((init!.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("throws ApiError on non-ok response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("nope", { status: 404 }));
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
  });
});
