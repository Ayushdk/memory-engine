import { useEffect, useState } from "react";
import { api, ApiError, Workspace as WorkspaceType, WorkspaceArchive } from "../api";

export default function Workspace({ projectId }: { projectId: string }) {
  const [workspace, setWorkspace] = useState<WorkspaceType | null>(null);
  const [archives, setArchives] = useState<WorkspaceArchive[]>([]);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setError(null);
    api
      .getWorkspace(projectId)
      .then(setWorkspace)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    api.listWorkspaceArchives(projectId).then(setArchives).catch(() => {});
  }

  useEffect(reload, [projectId]);

  return (
    <div>
      <h2>Workspace</h2>
      {error && <p className="error">{error}</p>}
      {workspace && (
        <div className="card">
          {workspace.goal && (
            <p>
              <strong>Goal:</strong> {workspace.goal}
            </p>
          )}
          {workspace.blockers.length > 0 && (
            <p>
              <strong>Blockers:</strong> {workspace.blockers.join(", ")}
            </p>
          )}
          <p>
            <strong>Internal summary</strong>
          </p>
          <pre>{workspace.internal_summary}</pre>
          <p>
            <strong>Transfer summary</strong>
          </p>
          <pre>{workspace.transfer_summary}</pre>
          <p className="muted">Updated {workspace.updated_at}</p>
          <button
            className="action"
            onClick={() => api.resetWorkspace(projectId).then(reload)}
          >
            Reset
          </button>{" "}
          <button
            className="action"
            onClick={() => api.archiveWorkspace(projectId).then(reload)}
          >
            Archive
          </button>
        </div>
      )}
      {archives.length > 0 && (
        <>
          <h3>Archives</h3>
          <ul className="plain">
            {archives.map((a) => (
              <li key={a.id}>
                <span className="muted">{a.archived_at}</span> — {a.transfer_summary}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
