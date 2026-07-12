import { useEffect, useState } from "react";
import { api, ApiConfig, loadConfig, saveConfig, Project } from "./api";
import Workspace from "./views/Workspace";
import ProjectBrain from "./views/ProjectBrain";
import PersonalBrain from "./views/PersonalBrain";
import Timeline from "./views/Timeline";
import ProjectStateHistory from "./views/ProjectStateHistory";
import ContextGeneration from "./views/ContextGeneration";

const TABS = [
  { id: "workspace", label: "Workspace" },
  { id: "project-brain", label: "Project Brain" },
  { id: "personal-brain", label: "Personal Brain" },
  { id: "timeline", label: "Timeline" },
  { id: "project-state", label: "Project State" },
  { id: "context", label: "Generate Context" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [config, setConfig] = useState<ApiConfig>(loadConfig());
  const [status, setStatus] = useState<"ok" | "bad" | "unknown">("unknown");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [tab, setTab] = useState<TabId>("workspace");

  useEffect(() => {
    saveConfig(config);
  }, [config]);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then(() => !cancelled && setStatus("ok"))
      .catch(() => !cancelled && setStatus("bad"));
    api
      .listProjects()
      .then((ps) => {
        if (cancelled) return;
        setProjects(ps);
        if (!projectId && ps.length > 0) setProjectId(ps[0].id);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // re-check whenever connection config changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.baseUrl, config.token]);

  return (
    <div className="app">
      <div className="topbar">
        <span className={`status-dot ${status}`} title={`engine: ${status}`} />
        <h1>OpenMemory</h1>
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
          <option value="">(no project)</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input
          type="text"
          style={{ width: "10rem" }}
          value={config.baseUrl}
          onChange={(e) => setConfig({ ...config, baseUrl: e.target.value })}
          placeholder="API base URL"
        />
        <input
          type="text"
          style={{ width: "12rem" }}
          value={config.token}
          onChange={(e) => setConfig({ ...config, token: e.target.value })}
          placeholder="API token"
        />
      </div>
      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={t.id === tab ? "active" : ""} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      <main>
        {!projectId && tab !== "personal-brain" && tab !== "context" && (
          <p className="muted">Select a project above — most views are project-scoped.</p>
        )}
        {tab === "workspace" && projectId && <Workspace projectId={projectId} />}
        {tab === "project-brain" && projectId && <ProjectBrain projectId={projectId} />}
        {tab === "personal-brain" && <PersonalBrain />}
        {tab === "timeline" && projectId && <Timeline projectId={projectId} />}
        {tab === "project-state" && projectId && <ProjectStateHistory projectId={projectId} />}
        {tab === "context" && <ContextGeneration projectId={projectId || null} />}
      </main>
    </div>
  );
}
