import { useState } from "react";
import { api, ApiError, ContextPack } from "../api";

export default function ContextGeneration({ projectId }: { projectId: string | null }) {
  const [sessionId, setSessionId] = useState("dashboard-preview");
  const [mode, setMode] = useState<"query" | "sync">("sync");
  const [query, setQuery] = useState("");
  const [pack, setPack] = useState<ContextPack | null>(null);
  const [error, setError] = useState<string | null>(null);

  function generate() {
    setError(null);
    api
      .generateContext({ session_id: sessionId, mode, query: query || undefined, project_id: projectId })
      .then(setPack)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  return (
    <div>
      <h2>Generate Context</h2>
      <div className="card">
        <input
          type="text"
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          placeholder="session id"
        />
        <select value={mode} onChange={(e) => setMode(e.target.value as "query" | "sync")}>
          <option value="sync">sync</option>
          <option value="query">query</option>
        </select>
        {mode === "query" && (
          <textarea value={query} onChange={(e) => setQuery(e.target.value)} placeholder="query text" />
        )}
        <button className="action" onClick={generate}>
          Generate
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {pack && (
        <div className="card">
          <p className="muted">
            {pack.token_estimate} tokens · {pack.delta ? "delta" : "full"} · {pack.generated_at}
          </p>
          {pack.sections.project_state && (
            <>
              <strong>Project state</strong>
              <pre>{pack.sections.project_state}</pre>
            </>
          )}
          {pack.sections.workspace && (
            <>
              <strong>Workspace</strong>
              <pre>{pack.sections.workspace}</pre>
            </>
          )}
          {pack.sections.profile.length > 0 && (
            <>
              <strong>Personal Brain</strong>
              <ul className="plain">
                {pack.sections.profile.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </>
          )}
          {pack.sections.relevant_memories.length > 0 && (
            <>
              <strong>Relevant memories</strong>
              <ul className="plain">
                {pack.sections.relevant_memories.map((m, i) => (
                  <li key={i}>
                    <span className="badge">{m.category}</span>
                    {m.summary}
                  </li>
                ))}
              </ul>
            </>
          )}
          {pack.sections.open_questions.length > 0 && (
            <>
              <strong>Open questions</strong>
              <ul className="plain">
                {pack.sections.open_questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </>
          )}
          <details>
            <summary>Raw JSON</summary>
            <pre>{JSON.stringify(pack, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  );
}
