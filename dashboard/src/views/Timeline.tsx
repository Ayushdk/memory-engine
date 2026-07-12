import { useEffect, useState } from "react";
import { api, Episode } from "../api";

export default function Timeline({ projectId }: { projectId: string }) {
  const [episodes, setEpisodes] = useState<Episode[]>([]);

  useEffect(() => {
    api.listEpisodes({ project_id: projectId, limit: 50 }).then(setEpisodes);
  }, [projectId]);

  return (
    <div>
      <h2>Timeline</h2>
      <ul className="plain">
        {episodes.map((e) => (
          <li key={e.id}>
            <span className="badge">{e.status}</span>
            <span className="muted">{e.started_at}</span>
            {e.platform && <span className="badge">{e.platform}</span>}
            <div>{e.summary_internal ?? <span className="muted">no summary yet</span>}</div>
          </li>
        ))}
      </ul>
      {episodes.length === 0 && <p className="muted">No episodes.</p>}
    </div>
  );
}
