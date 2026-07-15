import { useEffect, useMemo, useState } from "react";
import {
  api,
  ApiConfig,
  ContextPack,
  CurrentContextData,
  loadConfig,
  Memory,
  MemoryStatus,
  OverviewData,
  ProjectDashboardRow,
  Project,
  saveConfig,
  SearchResults,
} from "./api";
import { renderPack } from "../../extension/lib/pack-renderer.js";

const NAV = [
  ["overview", "Overview"],
  ["current", "Current Context"],
  ["projects", "Projects"],
  ["memories", "Memories"],
  ["timeline", "Timeline"],
  ["search", "Search"],
  ["diagnostics", "Diagnostics"],
  ["settings", "Settings"],
  ["preview", "Preview Sync"],
] as const;

type Page = (typeof NAV)[number][0];
type LoadState<T> = { data: T | null; error: string | null; loading: boolean };

const EMPTY_LOAD = { data: null, error: null, loading: false };
const MEMORY_GROUPS = {
  Preferences: ["preference"],
  "Technical Decisions": ["decision", "architecture", "constraint", "code"],
  Facts: ["fact", "insight"],
  "Long-term Knowledge": ["learning", "research", "document", "meeting", "goal", "milestone"],
  "Open Questions": ["question", "open_question", "task", "bug", "idea"],
};

export default function App() {
  const [config, setConfig] = useState<ApiConfig>(loadConfig());
  const [page, setPage] = useState<Page>("overview");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState<"ok" | "bad" | "unknown">("unknown");

  useEffect(() => saveConfig(config), [config]);

  useEffect(() => {
    let cancelled = false;
    api.health().then(() => !cancelled && setStatus("ok")).catch(() => !cancelled && setStatus("bad"));
    api.listProjects().then((rows) => {
      if (cancelled) return;
      setProjects(Array.isArray(rows) ? rows : []);
      if (!projectId && Array.isArray(rows) && rows[0]) setProjectId(rows[0].id);
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [config.baseUrl, config.token]);

  return (
    <div className="app">
      <header className="topbar">
        <span className={`status-dot ${status}`} title={`engine: ${status}`} />
        <h1>OpenMemory</h1>
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input value={config.baseUrl} onChange={(e) => setConfig({ ...config, baseUrl: e.target.value })} />
        <input value={config.token} onChange={(e) => setConfig({ ...config, token: e.target.value })} placeholder="API token" />
      </header>
      <nav className="tabs">
        {NAV.map(([id, label]) => (
          <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>
            {label}
          </button>
        ))}
      </nav>
      <main>
        {page === "overview" && <Overview />}
        {page === "current" && <CurrentContext />}
        {page === "projects" && <Projects selectedProjectId={projectId} onSelectProject={setProjectId} />}
        {page === "memories" && <Memories projectId={projectId} />}
        {page === "timeline" && <Timeline projectId={projectId} />}
        {page === "search" && <Search projectId={projectId} />}
        {page === "diagnostics" && <JsonPanel title="Diagnostics" loader={api.diagnostics} />}
        {page === "settings" && <Settings />}
        {page === "preview" && <PreviewSync projectId={projectId || null} />}
      </main>
    </div>
  );
}

function useLoad<T>(loader: () => Promise<T>, deps: unknown[] = []): LoadState<T> & { refresh: () => void } {
  const [state, setState] = useState<LoadState<T>>(EMPTY_LOAD);
  const refresh = () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    loader()
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error: String(error?.message ?? error), loading: false }));
  };
  useEffect(refresh, deps);
  return { ...state, refresh };
}

function Overview() {
  const { data, error, loading, refresh } = useLoad<OverviewData>(api.overview, []);
  const metrics: [string, string | number][] = data ? [
    ["Engine Status", data.engine_status],
    ["Current Platform", data.current_platform ?? "none"],
    ["Current Session", data.current_session ?? "none"],
    ["Current Project", data.current_project ?? "none"],
    ["Memory Capture", data.memory_capture_status],
    ["Last Sync", formatDate(data.last_sync)],
    ["Summary Status", data.conversation_summary_status],
    ["Total Projects", data.total_projects],
    ["Total Memories", data.total_memories],
    ["Total Conversations", data.total_conversations],
    ["Database Health", data.database_health],
  ] : [];
  return <section>
    <Title title="Overview" action={refresh} />
    <State error={error} loading={loading} />
    <div className="metric-grid">{metrics.map(([k, v]) => <Metric key={k} label={k} value={String(v)} />)}</div>
  </section>;
}

function CurrentContext() {
  const { data, error, loading, refresh } = useLoad<CurrentContextData>(api.currentContext, []);
  const copy = () => navigator.clipboard?.writeText(data?.conversation_summary ?? "");
  return <section>
    <Title title="Current Context" action={refresh} />
    <State error={error} loading={loading} />
    <div className="toolbar">
      <button className="action" onClick={copy}>Copy</button>
      <button className="action" onClick={refresh}>Refresh</button>
      <button className="action" disabled title="Backend-owned operation">Regenerate</button>
    </div>
    <div className="metric-grid compact">
      <Metric label="Last Updated" value={formatDate(data?.last_updated)} />
      <Metric label="Word Count" value={String(data?.word_count ?? 0)} />
      <Metric label="Character Count" value={String(data?.character_count ?? 0)} />
    </div>
    <article className="panel"><pre>{data?.conversation_summary || "No conversation summary has been created yet."}</pre></article>
  </section>;
}

function Projects({ selectedProjectId, onSelectProject }: { selectedProjectId: string; onSelectProject: (id: string) => void }) {
  const { data, error, loading, refresh } = useLoad<ProjectDashboardRow[]>(api.projectDashboard, []);
  const rows = data ?? [];
  const selected = rows.find((r) => r.project.id === selectedProjectId) ?? rows[0];
  return <section>
    <Title title="Projects" action={refresh} />
    <State error={error} loading={loading} />
    <div className="split">
      <ul className="plain project-list">{rows.map((r) => (
        <li key={r.project.id}>
          <button className={selected?.project.id === r.project.id ? "link active-link" : "link"} onClick={() => onSelectProject(r.project.id)}>
            <strong>{r.project.name}</strong><span className="muted">{formatDate(r.last_updated)}</span>
          </button>
        </li>
      ))}</ul>
      <div className="panel grow">
        {selected ? <>
          <h2>{selected.project.name}</h2>
          <Block title="Workspace Summary" text={selected.workspace_summary || "No workspace summary yet."} />
          <Block title="Project Brain" text={selected.project_brain || "No project brain snapshot yet."} />
          <List title="Recent Conversations" items={selected.recent_conversations.map((e) => `${e.status} · ${e.summary_internal || e.id}`)} />
          <List title="Important Memories" items={selected.important_memories.map((m) => m.summary || m.content)} />
        </> : <p className="muted">No projects yet.</p>}
      </div>
    </div>
  </section>;
}

function Memories({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<MemoryStatus>("active");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("updated");
  const { data, error, loading, refresh } = useLoad(() => api.listMemories({ project_id: projectId || undefined, status, limit: 1000 }), [projectId, status]);
  const memories = useMemo(() => {
    const q = query.toLowerCase();
    const rows = (data?.memories ?? []).filter((m) => !q || `${m.content} ${m.summary ?? ""} ${m.category}`.toLowerCase().includes(q));
    return rows.sort((a, b) => sort === "importance" ? b.importance - a.importance : Date.parse(b.updated_at) - Date.parse(a.updated_at));
  }, [data, query, sort]);
  return <section>
    <Title title="Memories" action={refresh} />
    <div className="toolbar">
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search memories" />
      <select value={status} onChange={(e) => setStatus(e.target.value as MemoryStatus)}><option>active</option><option>superseded</option><option>archived</option><option>merged</option></select>
      <select value={sort} onChange={(e) => setSort(e.target.value)}><option value="updated">Last updated</option><option value="importance">Importance</option></select>
    </div>
    <State error={error} loading={loading} />
    {Object.entries(MEMORY_GROUPS).map(([group, cats]) => (
      <MemoryGroup key={group} title={group} memories={memories.filter((m) => cats.includes(m.category))} />
    ))}
  </section>;
}

function Timeline({ projectId }: { projectId: string }) {
  const { data: episodes, error, loading, refresh } = useLoad(() => api.listEpisodes({ project_id: projectId || undefined, limit: 100 }), [projectId]);
  const stages = ["Captured Messages", "Episode Created", "Conversation Summary Updated", "Workspace Updated", "Project Brain Updated", "Sync Performed", "Injected Into AI"];
  return <section>
    <Title title="Timeline" action={refresh} />
    <State error={error} loading={loading} />
    <ol className="pipeline">{stages.map((s) => <li key={s}>{s}</li>)}</ol>
    <ul className="plain">{(episodes ?? []).map((e) => <li key={e.id}><span className="badge">{e.status}</span><span className="muted">{formatDate(e.started_at)}</span><p>{e.summary_internal || "Episode has not been summarized yet."}</p></li>)}</ul>
  </section>;
}

function Search({ projectId }: { projectId: string }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = () => q.trim() && api.dashboardSearch({ q: q.trim(), project_id: projectId || undefined }).then(setResults).catch((e) => setError(String(e.message ?? e)));
  return <section>
    <h2>Search</h2>
    <div className="toolbar"><input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()} placeholder="Search summaries, workspaces, memories, projects" /><button className="action" onClick={run}>Search</button></div>
    <State error={error} loading={false} />
    {results && <>
      <List title="Conversation Summaries" items={results.conversation_summaries.map((r) => r.summary)} />
      <List title="Workspaces" items={results.workspaces.map((r) => r.transfer_summary || r.internal_summary)} />
      <List title="Memories" items={results.memories.map((r) => r.summary || r.content)} />
      <List title="Projects" items={results.projects.map((r) => r.name)} />
    </>}
  </section>;
}

function Settings() {
  return <JsonPanel title="Settings" loader={api.settings} />;
}

function PreviewSync({ projectId }: { projectId: string | null }) {
  const [sessionId, setSessionId] = useState("dashboard-preview");
  const [pack, setPack] = useState<ContextPack | null>(null);
  const [error, setError] = useState<string | null>(null);
  const text = pack ? renderPack(pack) : "";
  const refresh = () => api.generateContext({ session_id: sessionId, mode: "sync", project_id: projectId }).then(setPack).catch((e) => setError(String(e.message ?? e)));
  return <section>
    <Title title="Preview Sync" action={refresh} />
    <div className="toolbar"><input value={sessionId} onChange={(e) => setSessionId(e.target.value)} placeholder="Session id" /><button className="action" onClick={() => navigator.clipboard?.writeText(text)}>Copy</button><button className="action" onClick={refresh}>Refresh</button><button className="action" onClick={refresh}>Sync</button></div>
    <State error={error} loading={false} />
    <article className="panel"><pre>{text || "No sync preview loaded."}</pre></article>
  </section>;
}

function JsonPanel({ title, loader }: { title: string; loader: () => Promise<Record<string, unknown>> }) {
  const { data, error, loading, refresh } = useLoad(loader, []);
  return <section><Title title={title} action={refresh} /><State error={error} loading={loading} /><article className="panel"><pre>{data ? JSON.stringify(data, null, 2) : ""}</pre></article></section>;
}

function Title({ title, action }: { title: string; action?: () => void }) {
  return <div className="section-title"><h2>{title}</h2>{action && <button className="action" onClick={action}>Refresh</button>}</div>;
}

function State({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <p className="error">{error}</p>;
  if (loading) return <p className="muted">Loading...</p>;
  return null;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function Block({ title, text }: { title: string; text: string }) {
  return <section className="block"><h3>{title}</h3><pre>{text}</pre></section>;
}

function List({ title, items }: { title: string; items: string[] }) {
  return <section className="block"><h3>{title}</h3>{items.length ? <ul className="plain">{items.map((item, i) => <li key={i}>{item}</li>)}</ul> : <p className="muted">None yet.</p>}</section>;
}

function MemoryGroup({ title, memories }: { title: string; memories: Memory[] }) {
  return <section className="panel"><h3>{title}</h3>{memories.length ? <ul className="plain">{memories.map((m) => <li key={m.id}><span className="badge">{m.category}</span><span className="badge">{m.confidence}</span>{m.summary || m.content}<span className="muted"> · {formatDate(m.updated_at)}</span></li>)}</ul> : <p className="muted">No matching memories.</p>}</section>;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
