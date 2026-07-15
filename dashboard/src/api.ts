// Thin fetch wrapper over the engine's REST API (app/api/routes). Types
// mirror the Pydantic response models field-for-field (no alias generator
// on the backend, so JSON keys are already snake_case).

export type MemoryView = "working" | "profile" | "project" | "episodic" | "semantic";
export type MemoryStatus = "active" | "superseded" | "archived" | "merged";
export type Confidence = "high" | "medium" | "low";

export interface Memory {
  id: string;
  content: string;
  summary: string | null;
  category: string;
  view: MemoryView;
  project_id: string | null;
  importance: number;
  confidence: Confidence;
  status: MemoryStatus;
  supersedes: string | null;
  source: {
    platform: string;
    session_id: string | null;
    role: "user" | "assistant";
    episode_id: string | null;
  } | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  last_accessed_at: string | null;
  access_count: number;
  reinforcement_count: number;
}

export interface Episode {
  id: string;
  session_id: string;
  project_id: string | null;
  platform: string | null;
  status: "open" | "closed" | "summarized";
  boundary_reason: string | null;
  message_count: number;
  started_at: string;
  ended_at: string | null;
  summary_internal: string | null;
}

export interface Workspace {
  project_id: string;
  internal_summary: string;
  transfer_summary: string;
  goal: string | null;
  blockers: string[];
  updated_at: string;
}

export interface WorkspaceArchive {
  id: string;
  project_id: string;
  internal_summary: string;
  transfer_summary: string;
  goal: string | null;
  blockers: string[];
  archived_at: string;
}

export interface ProjectState {
  id: string;
  project_id: string;
  version: number;
  content: string;
  generated_from: string[];
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  status: "active" | "archived";
  state: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ContextPack {
  session_id: string;
  generated_at: string;
  delta: boolean;
  token_estimate: number;
  sections: {
    project_state: string | null;
    workspace: string | null;
    conversation_summary?: string | null;
    profile: string[];
    relevant_memories: { category: string; summary: string; confidence: Confidence }[];
    open_questions: string[];
    recent_conversation: { platform: string; minutes_ago: number; messages: string[] } | null;
  };
}

export interface OverviewData {
  engine_status: string;
  current_platform: string | null;
  current_session: string | null;
  current_project: string | null;
  memory_capture_status: string;
  last_sync: string | null;
  conversation_summary_status: string;
  conversation_summary_updated_at: string | null;
  total_projects: number;
  total_memories: number;
  total_conversations: number;
  database_health: string;
  embedding_model: string;
  llm_model: string;
}

export interface CurrentContextData {
  session_id: string | null;
  conversation_summary: string;
  last_updated: string | null;
  word_count: number;
  character_count: number;
}

export interface ProjectDashboardRow {
  project: Project;
  workspace_summary: string;
  project_brain: string;
  recent_conversations: Episode[];
  important_memories: Memory[];
  last_updated: string;
}

export interface SearchResults {
  conversation_summaries: { session_id: string; summary: string; updated_at: string }[];
  workspaces: {
    project_id: string;
    transfer_summary: string;
    internal_summary: string;
    updated_at: string;
  }[];
  memories: {
    id: string;
    content: string;
    summary: string | null;
    category: string;
    view: string;
    project_id: string | null;
    updated_at: string;
  }[];
  projects: { id: string; name: string; status: string; updated_at: string }[];
}

const CONFIG_KEY = "openmemory.dashboard.config";

export interface ApiConfig {
  baseUrl: string;
  token: string;
}

export function loadConfig(): ApiConfig {
  try {
    const raw = localStorage.getItem(CONFIG_KEY);
    if (raw) return JSON.parse(raw) as ApiConfig;
  } catch {
    // ignore corrupt storage, fall through to defaults
  }
  return { baseUrl: "/api/v1", token: "" };
}

export function saveConfig(config: ApiConfig): void {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { baseUrl, token } = loadConfig();
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  overview: () => request<OverviewData>("/dashboard/overview"),
  currentContext: (sessionId?: string) =>
    request<CurrentContextData>(`/dashboard/current-context?${qs({ session_id: sessionId })}`),
  projectDashboard: () => request<ProjectDashboardRow[]>("/dashboard/projects"),
  dashboardSearch: (params: { q: string; project_id?: string }) =>
    request<SearchResults>(`/dashboard/search?${qs(params)}`),
  diagnostics: () => request<Record<string, unknown>>("/dashboard/diagnostics"),
  settings: () => request<Record<string, unknown>>("/dashboard/settings"),
  listProjects: () => request<Project[]>("/projects"),
  listMemories: (params: { view?: MemoryView; project_id?: string; status?: MemoryStatus; limit?: number }) =>
    request<{ memories: Memory[]; count: number }>(`/memories?${qs(params)}`),
  deleteMemory: (id: string) => request<unknown>(`/dashboard/memories/${id}`, { method: "DELETE" }),
  listEpisodes: (params: { project_id?: string; limit?: number }) =>
    request<Episode[]>(`/episodes?${qs(params)}`),
  getWorkspace: (projectId: string) => request<Workspace>(`/workspace/${projectId}`),
  resetWorkspace: (projectId: string) => request<Workspace>(`/workspace/${projectId}/reset`, { method: "POST" }),
  archiveWorkspace: (projectId: string) =>
    request<WorkspaceArchive>(`/workspace/${projectId}/archive`, { method: "POST" }),
  listWorkspaceArchives: (projectId: string) =>
    request<WorkspaceArchive[]>(`/workspace/${projectId}/archives`),
  getProjectState: (projectId: string) => request<ProjectState>(`/projects/${projectId}/state`),
  listProjectStateVersions: (projectId: string) =>
    request<ProjectState[]>(`/projects/${projectId}/state/versions`),
  generateContext: (body: { session_id: string; mode?: "query" | "sync"; query?: string; project_id?: string | null }) =>
    request<ContextPack>("/context", { method: "POST", body: JSON.stringify(body) }),
};

function qs(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  return usp.toString();
}
