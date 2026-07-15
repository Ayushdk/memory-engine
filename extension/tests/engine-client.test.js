import { describe, expect, it } from "vitest";

import { EngineClient, EngineError } from "../lib/engine-client.js";

/** fetch stub that records calls and returns a canned response. */
function fakeFetch(status = 200, body = { ok: true }) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    };
  };
  return { fn, calls };
}

function client(fetchStub, options = {}) {
  return new EngineClient({ fetchFn: fetchStub.fn, ...options });
}

describe("request shaping", () => {
  it("ingest maps camelCase to the engine's snake_case contract", async () => {
    const stub = fakeFetch();
    await client(stub).ingest({
      sessionId: "chatgpt-abc",
      platform: "chatgpt",
      role: "user",
      content: "We decided to use SQLite.",
      projectId: "proj_x",
    });

    const { url, init } = stub.calls[0];
    expect(url).toBe("http://127.0.0.1:8765/api/v1/ingest");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      session_id: "chatgpt-abc",
      platform: "chatgpt",
      role: "user",
      content: "We decided to use SQLite.",
      project_id: "proj_x",
      title: null,
    });
  });

  it("getSyncContext sends mode=sync and no query", async () => {
    const stub = fakeFetch();
    await client(stub).getSyncContext({ sessionId: "claude-1", projectId: null });
    const body = JSON.parse(stub.calls[0].init.body);
    expect(body).toEqual({ session_id: "claude-1", mode: "sync", project_id: null });
    expect("query" in body).toBe(false);
  });

  it("getContext sends mode=query with the query", async () => {
    const stub = fakeFetch();
    await client(stub).getContext({ sessionId: "s", query: "what did we decide?" });
    expect(JSON.parse(stub.calls[0].init.body)).toEqual({
      session_id: "s",
      mode: "query",
      query: "what did we decide?",
      project_id: null,
    });
  });

  it("getMemories builds query params only for provided filters", async () => {
    const stub = fakeFetch();
    await client(stub).getMemories({ projectId: "proj_x", limit: 20 });
    expect(stub.calls[0].url).toBe(
      "http://127.0.0.1:8765/api/v1/memories?project_id=proj_x&limit=20",
    );

    await client(stub).getMemories();
    expect(stub.calls[1].url).toBe("http://127.0.0.1:8765/api/v1/memories");
  });

  it("deleteMemory encodes the id into the path", async () => {
    const stub = fakeFetch();
    await client(stub).deleteMemory("mem_01ABC");
    expect(stub.calls[0].url).toBe("http://127.0.0.1:8765/api/v1/memories/mem_01ABC");
    expect(stub.calls[0].init.method).toBe("DELETE");
  });

  it("resetCapture encodes the session id into the reset path", async () => {
    const stub = fakeFetch();
    await client(stub).resetCapture("chatgpt/a b");
    expect(stub.calls[0].url).toBe("http://127.0.0.1:8765/api/v1/capture/chatgpt%2Fa%20b/reset");
    expect(stub.calls[0].init.method).toBe("POST");
  });

  it("listProjects reads the engine project list", async () => {
    const stub = fakeFetch(200, [{ id: "proj_om", name: "OpenMemory" }]);
    await client(stub).listProjects();
    expect(stub.calls[0].url).toBe("http://127.0.0.1:8765/api/v1/projects");
    expect(stub.calls[0].init.method).toBe("GET");
  });
});

describe("auth header", () => {
  it("sends the bearer token when configured", async () => {
    const stub = fakeFetch();
    await client(stub, { token: "s3cret" }).health();
    expect(stub.calls[0].init.headers["Authorization"]).toBe("Bearer s3cret");
  });

  it("omits the header when no token is set", async () => {
    const stub = fakeFetch();
    await client(stub).health();
    expect("Authorization" in stub.calls[0].init.headers).toBe(false);
  });
});

describe("configuration", () => {
  it("strips trailing slashes from the base url", async () => {
    const stub = fakeFetch();
    await client(stub, { baseUrl: "http://127.0.0.1:8765///" }).health();
    expect(stub.calls[0].url).toBe("http://127.0.0.1:8765/api/v1/health");
  });
});

describe("errors", () => {
  it("wraps HTTP errors with status and detail", async () => {
    const stub = fakeFetch(404, { detail: "memory 'mem_x' not found" });
    const error = await client(stub).deleteMemory("mem_x").catch((e) => e);
    expect(error).toBeInstanceOf(EngineError);
    expect(error.status).toBe(404);
    expect(error.detail).toBe("memory 'mem_x' not found");
    expect(error.unreachable).toBe(false);
  });

  it("maps network failure to status 0 / unreachable", async () => {
    const failing = async () => {
      throw new TypeError("fetch failed");
    };
    const error = await new EngineClient({ fetchFn: failing }).health().catch((e) => e);
    expect(error).toBeInstanceOf(EngineError);
    expect(error.status).toBe(0);
    expect(error.unreachable).toBe(true);
  });

  it("survives non-JSON error bodies", async () => {
    const stub = {
      fn: async () => ({ ok: false, status: 500, json: async () => Promise.reject(new Error("boom")) }),
      calls: [],
    };
    const error = await client(stub).health().catch((e) => e);
    expect(error.status).toBe(500);
    expect(error.detail).toBeNull();
  });
});
