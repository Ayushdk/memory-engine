import { useEffect, useState } from "react";
import { api, ApiError, ProjectState } from "../api";

export default function ProjectStateHistory({ projectId }: { projectId: string }) {
  const [versions, setVersions] = useState<ProjectState[]>([]);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setNotFound(false);
    api
      .listProjectStateVersions(projectId)
      .then(setVersions)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setNotFound(true);
      });
  }, [projectId]);

  return (
    <div>
      <h2>Project State</h2>
      {notFound && <p className="muted">No project state generated yet.</p>}
      {versions
        .slice()
        .reverse()
        .map((v) => (
          <div className="card" key={v.id}>
            <p>
              <strong>v{v.version}</strong> <span className="muted">{v.created_at}</span>
            </p>
            <pre>{v.content}</pre>
          </div>
        ))}
    </div>
  );
}
