/**
 * OpenMemory Engine API client.
 *
 * Platform-agnostic by design: knows the engine's HTTP contract and nothing
 * about ChatGPT/Claude/Gemini or chrome.* APIs, so every adapter reuses it
 * unchanged and it unit-tests in plain Node.
 */

export class EngineError extends Error {
  /**
   * @param {string} message
   * @param {number} status - HTTP status, or 0 when the engine is unreachable.
   * @param {unknown} [detail] - parsed error body when available.
   */
  constructor(message, status, detail = null) {
    super(message);
    this.name = "EngineError";
    this.status = status;
    this.detail = detail;
  }

  get unreachable() {
    return this.status === 0;
  }
}

export class EngineClient {
  /**
   * @param {object} options
   * @param {string} [options.baseUrl] - engine origin, no trailing slash needed.
   * @param {string|null} [options.token] - bearer token; null when auth is disabled.
   * @param {number} [options.timeoutMs]
   * @param {typeof fetch} [options.fetchFn] - injectable for tests.
   */
  constructor({ baseUrl = "http://127.0.0.1:8765", token = null, timeoutMs = 8000, fetchFn } = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.token = token;
    this.timeoutMs = timeoutMs;
    this._fetch = fetchFn ?? fetch.bind(globalThis);
  }

  async health() {
    return this._request("GET", "/api/v1/health");
  }

  /** @returns {Promise<object>} IngestionResult */
  async ingest({ sessionId, platform, role, content, projectId = null, title = null }) {
    return this._request("POST", "/api/v1/ingest", {
      session_id: sessionId,
      platform,
      role,
      content,
      project_id: projectId,
      title,
    });
  }

  /** Query-driven context (mid-conversation retrieval). */
  async getContext({ sessionId, query, projectId = null }) {
    return this._request("POST", "/api/v1/context", {
      session_id: sessionId,
      mode: "query",
      query,
      project_id: projectId,
    });
  }

  /**
   * State-driven Sync Context pack (no query). Sync closes the episode
   * inline, which chains up to three sequential local-LLM calls (episode
   * summary, workspace update, conversation summary) before responding —
   * on local Ollama that routinely exceeds the default request timeout, so
   * this gets its own, much longer budget instead of inheriting it.
   */
  async getSyncContext({ sessionId, projectId = null }) {
    return this._request(
      "POST",
      "/api/v1/context",
      { session_id: sessionId, mode: "sync", project_id: projectId },
      { timeoutMs: Math.max(this.timeoutMs, 90000) },
    );
  }

  /** @param {object} [filters] - view/projectId/category/status/limit */
  async getMemories({ view, projectId, category, status, limit } = {}) {
    const params = new URLSearchParams();
    if (view) params.set("view", view);
    if (projectId) params.set("project_id", projectId);
    if (category) params.set("category", category);
    if (status) params.set("status", status);
    if (limit) params.set("limit", String(limit));
    const qs = params.toString();
    return this._request("GET", `/api/v1/memories${qs ? `?${qs}` : ""}`);
  }

  async deleteMemory(memoryId) {
    return this._request("DELETE", `/api/v1/memories/${encodeURIComponent(memoryId)}`);
  }

  /** Projects the engine has seen work for (popup project dropdown). */
  async listProjects() {
    return this._request("GET", "/api/v1/projects");
  }

  /** Current working state of a project (summaries, goal, blockers). */
  async getWorkspace(projectId) {
    return this._request("GET", `/api/v1/workspace/${encodeURIComponent(projectId)}`);
  }

  async resetWorkspace(projectId) {
    return this._request("POST", `/api/v1/workspace/${encodeURIComponent(projectId)}/reset`);
  }

  async archiveWorkspace(projectId) {
    return this._request("POST", `/api/v1/workspace/${encodeURIComponent(projectId)}/archive`);
  }

  async _request(method, path, body = undefined, { timeoutMs = this.timeoutMs } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    let response;
    try {
      response = await this._fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (cause) {
      throw new EngineError(`engine unreachable at ${this.baseUrl}`, 0, cause);
    }

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail ?? payload;
      throw new EngineError(
        `engine responded ${response.status} on ${method} ${path}`,
        response.status,
        detail,
      );
    }
    return payload;
  }
}
