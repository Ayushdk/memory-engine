import { useEffect, useState } from "react";
import { api, Memory, MemoryStatus } from "../api";

export default function ProjectBrain({ projectId }: { projectId: string }) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [status, setStatus] = useState<MemoryStatus>("active");

  function reload() {
    api
      .listMemories({ view: "project", project_id: projectId, status })
      .then((r) => setMemories(r.memories));
  }

  useEffect(reload, [projectId, status]);

  return (
    <div>
      <h2>Project Brain</h2>
      <select value={status} onChange={(e) => setStatus(e.target.value as MemoryStatus)}>
        <option value="active">active</option>
        <option value="superseded">superseded</option>
        <option value="merged">merged</option>
        <option value="archived">archived</option>
      </select>
      <ul className="plain">
        {memories.map((m) => (
          <li key={m.id}>
            <span className="badge">{m.category}</span>
            <span className="badge">{m.confidence}</span>
            {m.content}
            {m.tags.length > 0 && <span className="muted"> [{m.tags.join(", ")}]</span>}{" "}
            <button
              className="action"
              onClick={() => api.deleteMemory(m.id).then(reload)}
            >
              delete
            </button>
          </li>
        ))}
      </ul>
      {memories.length === 0 && <p className="muted">No memories.</p>}
    </div>
  );
}
