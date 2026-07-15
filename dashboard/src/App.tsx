import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiConfig,
  CurrentContextData,
  Episode,
  loadConfig,
  Memory,
  MemoryStatus,
  OverviewData,
  ProjectDashboardRow,
  saveConfig,
  SearchResults,
} from "./api";

const NAV = [
  ["overview", "Overview"],
  ["activity", "Activity"],
  ["projects", "Projects"],
  ["settings", "Settings"],
] as const;

type Page = (typeof NAV)[number][0];
type ProjectTab = "summary" | "brain" | "conversations" | "memories";
type LoadState<T> = { data: T | null; error: string | null; loading: boolean };

const EMPTY_LOAD = { data: null, error: null, loading: false };
const THEME_KEY = "openmemory.dashboard.theme";

const MEMORY_GROUPS = {
  Preferences: ["preference"],
  "Technical Decisions": ["decision", "architecture", "constraint", "code"],
  Facts: ["fact", "insight"],
  "Long-term Knowledge": ["learning", "research", "document", "meeting", "goal", "milestone"],
  "Open Questions": ["question", "open_question", "task", "bug", "idea"],
};

export default function App() {
  const [config, setConfig] = useState<ApiConfig>(loadConfig());
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) ?? "system");
  const [page, setPage] = useState<Page>("overview");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectTab, setProjectTab] = useState<ProjectTab>("summary");
  const [status, setStatus] = useState<"ok" | "bad" | "unknown">("unknown");

  useEffect(() => saveConfig(config), [config]);

  useEffect(() => {
    localStorage.setItem(THEME_KEY, theme);
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    api.health().then(() => !cancelled && setStatus("ok")).catch(() => !cancelled && setStatus("bad"));
    return () => {
      cancelled = true;
    };
  }, [config.baseUrl, config.token]);

  function openProject(id: string | null, tab: ProjectTab = "summary") {
    setProjectId(id);
    setProjectTab(tab);
    setPage("projects");
  }

  function navigate(next: Page) {
    if (next === "projects") setProjectId(null);
    setPage(next);
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">M</span>
          <div className="brand-text">
            <strong>OpenMemory</strong>
            <span>Your work, remembered</span>
          </div>
        </div>
        <nav>
          {NAV.map(([id, label]) => (
            <button key={id} className={page === id ? "nav-item active" : "nav-item"} onClick={() => navigate(id)}>
              <Icon name={id} />
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className={`status-pill ${status}`}>
            {status === "ok" ? "Engine connected" : status === "bad" ? "Engine offline" : "Connecting…"}
          </span>
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <GlobalSearch onOpenProject={openProject} onGoTo={navigate} />
        </header>
        <main>
          {page === "overview" && <Overview onOpenProject={openProject} onGoTo={navigate} />}
          {page === "activity" && <Activity />}
          {page === "projects" && (
            projectId
              ? <ProjectWorkspace projectId={projectId} tab={projectTab} onTab={setProjectTab} onBack={() => setProjectId(null)} />
              : <ProjectsIndex onOpenProject={openProject} />
          )}
          {page === "settings" && <Settings config={config} onConfigChange={setConfig} theme={theme} onTheme={setTheme} />}
        </main>
      </div>
    </div>
  );
}

/* ---------------- Global search (topbar, no dedicated page) ---------------- */

function GlobalSearch({ onOpenProject, onGoTo }: {
  onOpenProject: (id: string | null, tab?: ProjectTab) => void;
  onGoTo: (page: Page) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const query = q.trim();
    if (!query) {
      setResults(null);
      setOpen(false);
      return;
    }
    const t = setTimeout(() => {
      api.dashboardSearch({ q: query })
        .then((r) => { setResults(r); setOpen(true); })
        .catch(() => setResults(null));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function pick(action: () => void) {
    setOpen(false);
    setQ("");
    action();
  }

  const empty = results && !results.projects.length && !results.memories.length
    && !results.conversation_summaries.length && !results.workspaces.length;

  return (
    <div className="global-search" ref={boxRef}>
      <Icon name="search" />
      <input
        value={q}
        role="searchbox"
        aria-label="Search"
        placeholder="Search projects, knowledge, conversations, memories…"
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => results && setOpen(true)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
      />
      {open && results && (
        <div className="search-results" role="listbox">
          {empty && <p className="muted search-empty">Nothing found for “{q.trim()}”.</p>}
          <SearchGroup label="Projects" items={results.projects.map((p) => ({
            key: p.id, title: p.name, sub: relativeTime(p.updated_at),
            go: () => pick(() => onOpenProject(p.id)),
          }))} />
          <SearchGroup label="Project Knowledge" items={results.workspaces.map((w) => ({
            key: w.project_id, title: w.transfer_summary || w.internal_summary, sub: w.project_id,
            go: () => pick(() => onOpenProject(w.project_id, "brain")),
          }))} />
          <SearchGroup label="Conversations" items={results.conversation_summaries.map((s) => ({
            key: s.session_id, title: s.summary, sub: relativeTime(s.updated_at),
            go: () => pick(() => onGoTo("activity")),
          }))} />
          <SearchGroup label="Memories" items={results.memories.map((m) => ({
            key: m.id, title: m.summary || m.content, sub: humanize(m.category),
            go: () => pick(() => m.project_id ? onOpenProject(m.project_id, "memories") : onGoTo("projects")),
          }))} />
        </div>
      )}
    </div>
  );
}

function SearchGroup({ label, items }: {
  label: string;
  items: { key: string; title: string; sub: string; go: () => void }[];
}) {
  if (!items.length) return null;
  return (
    <div className="search-group">
      <span className="search-group-label">{label}</span>
      {items.slice(0, 5).map((item) => (
        <button key={item.key} className="search-hit" onClick={item.go}>
          <span className="search-hit-title">{item.title}</span>
          <span className="muted">{item.sub}</span>
        </button>
      ))}
    </div>
  );
}

/* ---------------- Overview: "what was I working on, how do I continue?" ---------------- */

function Overview({ onOpenProject, onGoTo }: {
  onOpenProject: (id: string | null) => void;
  onGoTo: (page: Page) => void;
}) {
  const overview = useLoad<OverviewData>(api.overview, []);
  const context = useLoad<CurrentContextData>(() => api.currentContext(), []);
  const projects = useLoad<ProjectDashboardRow[]>(api.projectDashboard, []);
  const episodes = useLoad<Episode[]>(() => api.listEpisodes({ limit: 50 }), []);

  const rows = projects.data ?? [];
  const lastProject = overview.data?.current_project
    ? rows.find((r) => r.project.id === overview.data!.current_project) ?? rows[0]
    : rows[0];
  // Preview is a truncated view of the ALREADY generated latest conversation
  // summary (workspace summary as fallback) — never a second summary.
  const preview = context.data?.conversation_summary || lastProject?.workspace_summary || "";
  const activity = useMemo(
    () => buildActivity(episodes.data ?? [], rows).slice(0, 3),
    [episodes.data, rows],
  );

  return <section>
    <State error={overview.error} loading={overview.loading && !overview.data} />
    <article className="hero panel">
      <div className="hero-head">
        <div>
          <span className="hero-kicker">Pick up where you left off</span>
          <h2>{lastProject ? lastProject.project.name : "No project activity yet"}</h2>
          <p className="muted">
            {preview
              ? `Last updated ${relativeTime(context.data?.last_updated ?? lastProject?.last_updated)}`
              : "Start a conversation with the extension enabled and OpenMemory will remember it here."}
          </p>
        </div>
        {lastProject && (
          <button className="action primary" onClick={() => onOpenProject(lastProject.project.id)}>
            Continue →
          </button>
        )}
      </div>
      {preview && <p className="hero-preview">{preview}</p>}
    </article>

    <div className="block">
      <div className="block-head">
        <h3>Recent Activity</h3>
        <button className="text-link" onClick={() => onGoTo("activity")}>View all</button>
      </div>
      {activity.length
        ? <ul className="plain">{activity.map((a) => (
            <li key={a.id} className="activity-row">
              <span className="muted activity-when">{relativeTime(a.when)}</span>
              <div>
                <strong>{a.title}</strong>
                <p className="clamp-3">{a.content}</p>
              </div>
            </li>
          ))}</ul>
        : <p className="muted">No activity yet.</p>}
    </div>

    <div className="block">
      <div className="block-head">
        <h3>Projects</h3>
        <button className="text-link" onClick={() => onGoTo("projects")}>View all</button>
      </div>
      <div className="project-grid">
        {rows.slice(0, 6).map((r) => <ProjectCard key={r.project.id} row={r} onOpen={() => onOpenProject(r.project.id)} />)}
        {!projects.loading && !rows.length && <p className="muted">No projects yet — set a project in the extension popup.</p>}
      </div>
    </div>
  </section>;
}

/* ---------------- Activity: the history of meaningful work ---------------- */

type ActivityItem = {
  id: string;
  when: string;
  title: string;
  kind: "conversation" | "brain" | "project";
  project: string | null;
  content: string;
};

function buildActivity(episodes: Episode[], rows: ProjectDashboardRow[]): ActivityItem[] {
  const items: ActivityItem[] = [];
  for (const e of episodes) {
    if (e.status === "summarized" && e.summary_internal) {
      items.push({
        id: `ep-${e.id}`,
        when: e.ended_at ?? e.started_at,
        title: "Conversation Summary Updated",
        kind: "conversation",
        project: e.project_id,
        content: e.summary_internal,
      });
    }
  }
  for (const r of rows) {
    if (r.project_brain) {
      items.push({
        id: `brain-${r.project.id}`,
        when: r.last_updated,
        title: `Project Brain Updated — ${r.project.name}`,
        kind: "brain",
        project: r.project.id,
        content: r.project_brain,
      });
    }
    items.push({
      id: `proj-${r.project.id}`,
      when: r.project.created_at,
      title: `Project Created — ${r.project.name}`,
      kind: "project",
      project: r.project.id,
      content: r.workspace_summary || r.project.name,
    });
  }
  return items.sort((a, b) => Date.parse(b.when) - Date.parse(a.when));
}

const ACTIVITY_FILTERS = [
  ["", "All"],
  ["conversation", "Conversations"],
  ["brain", "Project Brain"],
  ["project", "Projects"],
] as const;

function Activity() {
  const [filter, setFilter] = useState<string>("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const episodes = useLoad<Episode[]>(() => api.listEpisodes({ limit: 200 }), []);
  const projects = useLoad<ProjectDashboardRow[]>(api.projectDashboard, []);
  const items = useMemo(
    () => buildActivity(episodes.data ?? [], projects.data ?? []).filter((a) => !filter || a.kind === filter),
    [episodes.data, projects.data, filter],
  );

  return <section>
    <div className="toolbar">
      <div className="chip-row">
        {ACTIVITY_FILTERS.map(([value, label]) => (
          <button key={value} className={filter === value ? "chip active" : "chip"} onClick={() => setFilter(value)}>
            {label}
          </button>
        ))}
      </div>
      <button className="action" onClick={() => { episodes.refresh(); projects.refresh(); }}>Refresh</button>
    </div>
    <State error={episodes.error} loading={episodes.loading && !episodes.data} />
    {!episodes.loading && !items.length && (
      <div className="empty-state"><div className="empty-icon" aria-hidden="true" /><h3>No activity yet.</h3></div>
    )}
    <ul className="plain">
      {items.map((a) => (
        <li key={a.id} className="activity-row">
          <span className="muted activity-when" title={formatDate(a.when)}>{relativeTime(a.when)}</span>
          <div className="grow">
            <div className="activity-title">
              <strong>{a.title}</strong>
              <button className="text-link" onClick={() => navigator.clipboard?.writeText(a.content)}>Copy</button>
            </div>
            <p
              className={expanded === a.id ? "" : "clamp-3"}
              onClick={() => setExpanded(expanded === a.id ? null : a.id)}
              title={expanded === a.id ? "Click to collapse" : "Click to expand"}
            >
              {a.content}
            </p>
          </div>
        </li>
      ))}
    </ul>
  </section>;
}

/* ---------------- Projects: the heart of OpenMemory ---------------- */

function ProjectsIndex({ onOpenProject }: { onOpenProject: (id: string) => void }) {
  const { data, error, loading, refresh } = useLoad<ProjectDashboardRow[]>(api.projectDashboard, []);
  const rows = data ?? [];
  return <section>
    <div className="section-title"><button className="action" onClick={refresh}>Refresh</button></div>
    <State error={error} loading={loading && !data} />
    <div className="project-grid">
      {rows.map((r) => <ProjectCard key={r.project.id} row={r} onOpen={() => onOpenProject(r.project.id)} />)}
    </div>
    {!loading && !rows.length && (
      <div className="empty-state">
        <div className="empty-icon" aria-hidden="true" />
        <h3>No projects yet.</h3>
        <p className="muted">Set a project in the extension popup and start chatting.</p>
      </div>
    )}
  </section>;
}

function ProjectCard({ row, onOpen }: { row: ProjectDashboardRow; onOpen: () => void }) {
  return (
    <button className="project-card" onClick={onOpen}>
      <strong>{row.project.name}</strong>
      <p className="clamp-3">{row.workspace_summary || "No summary yet — it will appear after the first synced conversation."}</p>
      <span className="muted">Updated {relativeTime(row.last_updated)}</span>
    </button>
  );
}

const PROJECT_TABS: [ProjectTab, string][] = [
  ["summary", "Summary"],
  ["brain", "Project Brain"],
  ["conversations", "Conversations"],
  ["memories", "Memories"],
];

function ProjectWorkspace({ projectId, tab, onTab, onBack }: {
  projectId: string;
  tab: ProjectTab;
  onTab: (t: ProjectTab) => void;
  onBack: () => void;
}) {
  const { data, error, loading, refresh } = useLoad<ProjectDashboardRow[]>(api.projectDashboard, [projectId]);
  const row = (data ?? []).find((r) => r.project.id === projectId);

  return <section>
    <div className="section-title workspace-head">
      <button className="text-link" onClick={onBack}>← All projects</button>
      <h2>{row?.project.name ?? projectId}</h2>
      <button className="action" onClick={refresh}>Refresh</button>
    </div>
    <div className="tabs" role="tablist">
      {PROJECT_TABS.map(([id, label]) => (
        <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "tab active" : "tab"} onClick={() => onTab(id)}>
          {label}
        </button>
      ))}
    </div>
    <State error={error} loading={loading && !data} />
    {row && tab === "summary" && (
      <article className="panel">
        {row.workspace_summary
          ? <pre>{row.workspace_summary}</pre>
          : <p className="muted">No summary yet. It evolves automatically as conversations are added to this project.</p>}
      </article>
    )}
    {row && tab === "brain" && <ProjectBrain text={row.project_brain} />}
    {row && tab === "conversations" && <ProjectConversations projectId={projectId} />}
    {tab === "memories" && <Memories projectId={projectId} />}
  </section>;
}

/** Render the brain document as collapsible chapters, split on markdown
 *  headings. The structure comes from the generated document itself — the UI
 *  imposes no template. */
function ProjectBrain({ text }: { text: string }) {
  const chapters = useMemo(() => splitChapters(text), [text]);
  if (!text) {
    return <article className="panel">
      <p className="muted">
        The Project Brain builds itself from your conversations. Nothing has been distilled for this project yet.
      </p>
    </article>;
  }
  if (chapters.length === 1 && !chapters[0].title) {
    return <article className="panel"><pre>{text}</pre></article>;
  }
  return <div>
    {chapters.map((c, i) => (
      <details key={i} className="chapter" open={i === 0}>
        <summary>{c.title || "Overview"}</summary>
        <pre>{c.body}</pre>
      </details>
    ))}
  </div>;
}

function splitChapters(text: string): { title: string; body: string }[] {
  const lines = (text ?? "").split("\n");
  const chapters: { title: string; body: string[] }[] = [];
  let current: { title: string; body: string[] } = { title: "", body: [] };
  for (const line of lines) {
    const heading = /^#{1,3}\s+(.*)/.exec(line);
    if (heading) {
      if (current.title || current.body.some((l) => l.trim())) chapters.push(current);
      current = { title: heading[1].trim(), body: [] };
    } else {
      current.body.push(line);
    }
  }
  if (current.title || current.body.some((l) => l.trim())) chapters.push(current);
  return chapters.map((c) => ({ title: c.title, body: c.body.join("\n").trim() }));
}

function ProjectConversations({ projectId }: { projectId: string }) {
  const { data, error, loading } = useLoad<Episode[]>(() => api.listEpisodes({ project_id: projectId, limit: 100 }), [projectId]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const conversations = (data ?? []).filter((e) => e.summary_internal);
  return <div>
    <State error={error} loading={loading && !data} />
    {!loading && !conversations.length && <p className="muted">No summarized conversations for this project yet.</p>}
    <ul className="plain">
      {conversations.map((e) => (
        <li key={e.id} className="activity-row">
          <span className="muted activity-when" title={formatDate(e.started_at)}>{relativeTime(e.ended_at ?? e.started_at)}</span>
          <div className="grow">
            <div className="activity-title">
              <strong>{e.platform ? `${humanize(e.platform)} conversation` : "Conversation"}</strong>
              <button className="text-link" onClick={() => navigator.clipboard?.writeText(e.summary_internal ?? "")}>Copy</button>
            </div>
            <p
              className={expanded === e.id ? "" : "clamp-3"}
              onClick={() => setExpanded(expanded === e.id ? null : e.id)}
            >
              {e.summary_internal}
            </p>
          </div>
        </li>
      ))}
    </ul>
  </div>;
}

/* ---------------- Memories (inside a project) ---------------- */

function Memories({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<MemoryStatus>("active");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [deletedIds, setDeletedIds] = useState<Set<string>>(() => new Set());
  const [confirmDelete, setConfirmDelete] = useState<Memory | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const { data, error, loading, refresh } = useLoad(
    () => api.listMemories({ project_id: projectId, status, limit: 1000 }),
    [projectId, status],
  );
  const allMemories = useMemo(
    () => (data?.memories ?? []).filter((memory) => !deletedIds.has(memory.id)),
    [data, deletedIds],
  );
  const categories = useMemo(() => unique(allMemories.map((m) => m.category)), [allMemories]);
  const memories = useMemo(() => {
    const q = query.toLowerCase();
    return allMemories
      .filter((m) => (!q || memorySearchText(m).includes(q)) && (!category || m.category === category))
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
  }, [allMemories, category, query]);

  async function deleteMemory(memory: Memory) {
    setDeletingId(memory.id);
    try {
      await api.deleteMemory(memory.id);
      setDeletedIds((ids) => new Set(ids).add(memory.id));
      setConfirmDelete(null);
    } finally {
      setDeletingId(null);
    }
  }

  return <div>
    <div className="toolbar">
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter memories" />
      <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
        <option value="">All types</option>
        {categories.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}
      </select>
      <select value={status} onChange={(e) => setStatus(e.target.value as MemoryStatus)} aria-label="Status">
        <option value="active">Active</option><option value="archived">Archived</option>
        <option value="superseded">Superseded</option><option value="merged">Merged</option>
      </select>
      <button className="action" onClick={() => { setDeletedIds(new Set()); refresh(); }}>Refresh</button>
    </div>
    <State error={error} loading={loading && !data} />
    {!loading && memories.length === 0 ? (
      <div className="empty-state"><div className="empty-icon" aria-hidden="true" /><h3>No memories found.</h3></div>
    ) : (
      <div className="memory-grid">
        {memories.map((memory) => (
          <MemoryCard key={memory.id} memory={memory} onDelete={() => setConfirmDelete(memory)} />
        ))}
      </div>
    )}
    {confirmDelete && (
      <DeleteMemoryDialog
        memory={confirmDelete}
        busy={deletingId === confirmDelete.id}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={() => deleteMemory(confirmDelete)}
      />
    )}
  </div>;
}

function MemoryCard({ memory, onDelete }: { memory: Memory; onDelete: () => void }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const text = memory.summary || memory.content;
  const isLong = text.length > 280;
  const visibleText = expanded || !isLong ? text : `${text.slice(0, 280).trim()}...`;

  function copyMemory() {
    void navigator.clipboard?.writeText(memory.content);
    setMenuOpen(false);
  }

  return (
    <article className="memory-card">
      <div className="memory-card-head">
        <div>
          <span className="memory-category">{humanize(categoryGroup(memory.category) ?? memory.category)}</span>
          <div className="memory-badges">
            <span className={`badge importance-${importanceBand(memory.importance)}`}>{humanize(importanceBand(memory.importance))}</span>
            <span className="badge">Confidence {humanize(memory.confidence)}</span>
          </div>
        </div>
        <div className="memory-menu-wrap">
          <button className="icon-button" aria-label="Memory actions" onClick={() => setMenuOpen((open) => !open)}>⋮</button>
          {menuOpen && (
            <div className="memory-menu">
              <button onClick={copyMemory}>Copy Memory</button>
              <button className="menu-danger" onClick={() => { setMenuOpen(false); onDelete(); }}>Delete Memory</button>
              <div className="menu-separator" />
              <span>Coming Soon</span>
              <button disabled>Edit Memory</button>
              <button disabled>Merge Memory</button>
              <button disabled>Archive Memory</button>
            </div>
          )}
        </div>
      </div>
      <p className="memory-text">{visibleText}</p>
      {isLong && <button className="text-link" onClick={() => setExpanded((v) => !v)}>{expanded ? "Collapse" : "Expand"}</button>}
      <dl className="memory-meta">
        <div><dt>Created</dt><dd>{relativeTime(memory.created_at)}</dd></div>
        <div><dt>Reinforced</dt><dd>{memory.reinforcement_count > 0 ? `${memory.reinforcement_count}×` : "Never"}</dd></div>
        <div><dt>Type</dt><dd>{humanize(memory.category)}</dd></div>
      </dl>
    </article>
  );
}

function DeleteMemoryDialog({ memory, busy, onCancel, onConfirm }: { memory: Memory; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="delete-memory-title">
        <h2 id="delete-memory-title">Delete Memory</h2>
        <p>Are you sure you want to permanently delete this memory?</p>
        <p className="error">This action cannot be undone.</p>
        <div className="memory-preview">
          <span>Memory Preview</span>
          <blockquote>{previewText(memory.summary || memory.content)}</blockquote>
        </div>
        <div className="modal-actions">
          <button className="action" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className="action destructive" onClick={onConfirm} disabled={busy}>{busy ? "Deleting..." : "Delete Memory"}</button>
        </div>
      </section>
    </div>
  );
}

/* ---------------- Settings: user-facing only ---------------- */

function Settings({ config, onConfigChange, theme, onTheme }: {
  config: ApiConfig;
  onConfigChange: (c: ApiConfig) => void;
  theme: string;
  onTheme: (t: string) => void;
}) {
  const engine = useLoad<Record<string, unknown>>(api.settings, []);
  const e = (engine.data?.engine ?? {}) as Record<string, Record<string, unknown>>;
  return <section>
    <article className="panel">
      <h3>Appearance</h3>
      <div className="settings-grid">
        <label htmlFor="cfg-theme">Theme</label>
        <select id="cfg-theme" value={theme} onChange={(ev) => onTheme(ev.target.value)}>
          <option value="system">System</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
      </div>
    </article>
    <article className="panel">
      <h3>Connection</h3>
      <div className="settings-grid">
        <label htmlFor="cfg-url">Engine URL</label>
        <input id="cfg-url" value={config.baseUrl} onChange={(ev) => onConfigChange({ ...config, baseUrl: ev.target.value })} />
        <label htmlFor="cfg-token">API token</label>
        <input id="cfg-token" type="password" value={config.token} onChange={(ev) => onConfigChange({ ...config, token: ev.target.value })} placeholder="Optional" />
      </div>
    </article>
    <article className="panel">
      <h3>Models</h3>
      <State error={engine.error} loading={engine.loading} />
      <div className="settings-grid">
        {Object.entries(e.active_models ?? {}).map(([k, v]) => (
          <ReadonlyRow key={k} label={humanize(k)} value={String(v)} />
        ))}
      </div>
    </article>
    <article className="panel">
      <h3>Sync</h3>
      <div className="settings-grid">
        {Object.entries({ ...(e.capture_settings ?? {}), ...(e.sync_settings ?? {}) }).map(([k, v]) => (
          <ReadonlyRow key={k} label={humanize(k)} value={String(v)} />
        ))}
      </div>
      <p className="muted">Model and sync values are configured in the engine's .env file.</p>
    </article>
    <article className="panel">
      <h3>Data</h3>
      <div className="chip-row">
        <button className="action" disabled title="Coming soon">Import</button>
        <button className="action" disabled title="Coming soon">Export</button>
        <button className="action destructive" disabled title="Coming soon">Delete Project</button>
      </div>
    </article>
  </section>;
}

function ReadonlyRow({ label, value }: { label: string; value: string }) {
  return <>
    <label>{label}</label>
    <span className="readonly-value">{value}</span>
  </>;
}

/* ---------------- Shared bits ---------------- */

const ICON_PATHS: Record<Page | "search", string> = {
  overview: "M3 10.5 12 3l9 7.5M5 9.5V21h14V9.5",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  projects: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35",
};

function Icon({ name }: { name: Page | "search" }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICON_PATHS[name]} />
    </svg>
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

function State({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <p className="error">{error}</p>;
  if (loading) {
    return <div className="skeleton-stack" aria-label="Loading" role="status">
      <div className="skeleton" /><div className="skeleton" /><div className="skeleton" />
    </div>;
  }
  return null;
}

function categoryGroup(category: string) {
  return Object.entries(MEMORY_GROUPS).find(([, categories]) => categories.includes(category))?.[0];
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function importanceBand(value: number) {
  if (value >= 8) return "high";
  if (value >= 4) return "medium";
  return "low";
}

function memorySearchText(memory: Memory) {
  return [memory.content, memory.summary ?? "", memory.category, memory.tags.join(" ")].join(" ").toLowerCase();
}

function relativeTime(value: string | null | undefined) {
  if (!value) return "never";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  const diff = Date.now() - timestamp;
  if (diff < 60_000) return "just now";
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  if (hours < 48) return "yesterday";
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

function previewText(value: string) {
  return value.length > 160 ? `${value.slice(0, 160).trim()}...` : value;
}

function unique(values: string[]) {
  return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b));
}

function formatDate(value: string | null | undefined) {
  if (!value) return "never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
