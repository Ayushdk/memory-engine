import { useEffect, useState } from "react";
import { api, Memory, MemoryStatus } from "../api";

export default function PersonalBrain() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [status, setStatus] = useState<MemoryStatus>("active");

  useEffect(() => {
    api.listMemories({ view: "profile", status }).then((r) => setMemories(r.memories));
  }, [status]);

  return (
    <div>
      <h2>Personal Brain</h2>
      <p className="muted">Cross-project — reinforced preferences promoted from Project Brains.</p>
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
            <span className="badge">reinforced x{m.reinforcement_count}</span>
            {m.content}
          </li>
        ))}
      </ul>
      {memories.length === 0 && <p className="muted">No memories.</p>}
    </div>
  );
}
