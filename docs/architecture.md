# OpenMemory Engine — Architecture (V1 Freeze)

> **Status: FROZEN.** This is the V1 specification. Do not redesign; build.
> Anything not listed here is explicitly out of V1 (see §9).

---

## 1. Locked design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Engine-first: FastAPI, extension, dashboard are all **clients** of `app/engine/` | Engine stays reusable (CLI, MCP, desktop later) |
| 2 | **One unified memory store**; memory types are logical views (filters), not tables | Gmail-labels model; avoids five-database sprawl |
| 3 | Classifier / Scorer are **swappable strategies**; V1 ships rules + heuristics | Zero cost, offline, deterministic, testable; LLM (Ollama/Gemini) drops in later behind the same interface |
| 4 | Embeddings are **local**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim, CPU) | Free forever, no data leaves the machine |
| 5 | SQLite = source of truth (metadata, relations, state); ChromaDB = index only (embeddings) | Chroma can always be rebuilt from SQLite |
| 6 | Reflection runs **async in background jobs**, never blocks ingestion or retrieval | Core latency insight |
| 7 | `confidence` field exists **from day one** (V1: `high` for explicit statements, `medium` for inferences) | Enables the V2 Confidence Engine without migration |
| 8 | Everything runs locally and free of cost: SQLite + embedded ChromaDB + local embeddings, no paid APIs | Project constraint |

## 2. System overview

```
                        USER (ChatGPT / Claude / Gemini)
                                     │
                          Browser Extension  (V1: manual copy-paste)
                                     │  HTTP JSON
                        ┌────────────▼────────────┐
                        │  FastAPI  localhost:8000 │   ← transport only, no logic
                        └────────────┬────────────┘
                        ┌────────────▼────────────┐
                        │      MEMORY ENGINE      │
                        │                         │
                        │  INGESTION PATH (sync, <100 ms)
                        │  WorkingMemory → Classifier → Scorer → Router → Store
                        │                         │
                        │  RETRIEVAL PATH (sync, <500 ms)
                        │  Retrieval → ContextBuilder → DeltaBuilder → ContextPack
                        │                         │
                        │  REFLECTION PATH (async, unbounded)
                        │  Dedup → Consolidation → ProjectState
                        └────────────┬────────────┘
                     ┌───────────────┴────────────────┐
                     │ SQLite (truth)  ChromaDB (index)│
                     └────────────────────────────────┘
```

Three paths, three latency budgets. Ingestion and retrieval are synchronous and fast
(no LLM in the loop); reflection is background maintenance and may take as long as it needs.

## 3. The Memory Object

The single schema every module shares. Memory types (working / profile / project /
episodic / semantic) are **views** computed from these fields, never separate stores.

```json
{
  "id": "mem_01J...",
  "content": "Selected FastAPI over Flask for the backend.",
  "summary": "Backend = FastAPI",
  "category": "decision",
  "view": "project",
  "project_id": "proj_openmemory",
  "importance": 9,
  "confidence": "high",
  "status": "active",
  "supersedes": "mem_01H...",
  "source": { "platform": "chatgpt", "session_id": "...", "role": "user" },
  "tags": ["backend", "architecture"],
  "created_at": "...",
  "updated_at": "...",
  "last_accessed_at": "...",
  "access_count": 3
}
```

- `id` is a ULID (time-sortable).
- `status` + `supersedes` implement "Update Existing Memory" non-destructively:
  an update creates a new memory and marks the old one `superseded`.
- `last_accessed_at` / `access_count` are written by the Retrieval Engine and feed reflection.
- The embedding is **not** stored here; it lives in ChromaDB keyed by the same `id`.

### Enums

- **category (14):** `decision, preference, goal, question, idea, meeting, bug, architecture, research, task, milestone, learning, code, document`
- **view (5):** `working, profile, project, episodic, semantic`
- **classifier action (5):** `IGNORE, STORE, UPDATE, MERGE, DELETE`
- **confidence (3):** `high, medium, low`
- **status (4):** `active, superseded, archived, merged`

## 4. Module specifications

| Module | Location | Input → Output | V1 implementation (free) | V2 upgrade |
|---|---|---|---|---|
| Working Memory Manager | `engine/working_memory/` | message → rolling session buffer | In-memory deque per session, cap 30, importance-weighted eviction; snapshot to SQLite so restarts don't lose it | Topic tracking |
| Memory Classifier | `engine/classifier/` | message → action + category | Rule table ("I decided / we'll use" → STORE decision; "switched / instead of" → UPDATE; greetings/acks → IGNORE). UPDATE detection = embedding similarity > 0.85 against active memories in same project | LLM strategy (Ollama / Gemini) behind same interface |
| Importance Scorer | `engine/scorer/` | classified memory → 0–10 | Rubric: base score per category (decision 9, architecture 9, preference 7, question 3…) ± modifiers (has project +1, "important" +1, question −1) | LLM scoring |
| Storage Router | `engine/router/` | scored memory → view + persistence | Deterministic mapping category × project × pronoun heuristics → `view`; writes SQLite first, Chroma second; repair job reconciles | — |
| Retrieval Engine | `engine/retrieval/` | query + project → top-K memories | Score = `0.45·cosine + 0.25·importance + 0.20·recency(exp decay) + 0.10·access_freq`, hard-filtered by project + status=active. Chroma top-40 candidates → re-rank → top 10–15 | Confidence weighting |
| Context Builder | `engine/context/` | memories + state → Context Pack | Fixed template: Project State → Profile facts → Relevant memories (grouped by category) → Open questions. Token budget ~1500, truncate lowest-scored first | Adaptive budgets |
| Delta Context Builder | `engine/context/` | pack + injection log → delta pack | `injections` table logs what was injected per session; new session = full pack, ongoing = only not-yet-injected memories | Semantic diffing |
| Reflection Engine | `engine/reflection/` | trigger → maintenance | Jobs: (a) dedup — cosine > 0.92 within view+project → MERGE, keep higher importance; (b) decay — importance ≤ 3 untouched 30 days → archive; (c) project state rebuild. Triggers: every 50 new memories or manual `POST /reflection/run` | LLM summarization |
| Knowledge Consolidation | `engine/project_state/` | project memories → Project State | Deterministic assembly: latest active decisions by tag + open questions + milestones → `projects.state_json` | LLM narrative summary |

**Strategy-swap contract:** classifier and scorer are called through one interface
(`classify(message, context) → ClassificationResult`); a config flag selects
`rules | ollama | gemini`. Pipeline code never knows which strategy is running.

## 5. Storage layer

### SQLite (`data/sqlite/openmemory.db`, WAL mode) — source of truth

| Table | Purpose |
|---|---|
| `memories` | Unified store — every field from §3 |
| `projects` | id, name, status, `state_json` (consolidated Project State) |
| `sessions` | session id, platform, started_at |
| `working_memory` | session snapshot (survives restart) |
| `injections` | what was injected where — powers the Delta Builder |
| `memory_relations` | supersedes / merged-into links |

### ChromaDB (`data/chroma/`, embedded persistent client — no server)

One collection `memories`: id = memory id, vector = MiniLM embedding,
metadata = `{view, project_id, importance, status}` for pre-filtering.
Fully rebuildable from SQLite (`scripts/reset_db.py`).

## 6. API surface (V1 — six endpoints)

```
POST   /api/v1/ingest          {session_id, platform, role, content} → {action, memory_id?, category?}
POST   /api/v1/context         {session_id, query, project_id?, delta?} → ContextPack
GET    /api/v1/memories        ?view=&project=&category=&q=   (browse/debug; powers future dashboard)
DELETE /api/v1/memories/{id}   (user's right to forget)
POST   /api/v1/reflection/run  (manual sync trigger)
GET    /api/v1/health
```

## 7. Context Pack format

```json
{
  "session_id": "...",
  "generated_at": "...",
  "delta": false,
  "token_estimate": 1240,
  "sections": {
    "project_state": "...",
    "profile": ["User prefers diagrams", "..."],
    "relevant_memories": [{ "category": "decision", "summary": "...", "confidence": "high" }],
    "open_questions": ["..."]
  }
}
```

The extension (or the user, in V1) renders this into a prompt preamble. Never the whole conversation.

## 8. Repository layout (post-prune)

```
app/
  main.py                     FastAPI app factory + router mounting
  api/                        transport only — no business logic
    dependencies.py           DI wiring (engine singletons)
    error_handlers.py
    routes/                   health, memory (ingest/browse/delete), context, reflection
  core/                       config (pydantic-settings), paths, logging, lifecycle
  engine/                     THE PRODUCT — importable without FastAPI
    orchestrator/
      ingestion_pipeline.py   WM → classify → score → route → store
      context_pipeline.py     retrieve → build → delta → ContextPack
    working_memory/           working_memory_manager, session_state
    classifier/               memory_classifier (interface), classification_rules (rule table)
    scorer/                   importance_scorer (interface), scoring_policy (rubric)
    router/                   storage_router
    retrieval/                retrieval_engine, ranking_engine
    context/                  context_builder, delta_context_builder
    reflection/               reflection_engine, memory_merger, consolidation_engine
    project_state/            project_state_manager
  memory/
    repositories/             memory_repository (unified), project_repository
    sqlite/                   connection, schema
    vector/                   chroma_client
  models/
    enums.py                  category / view / action / confidence / status
    domain/                   memory, project, context_pack (pydantic)
    schemas/                  API request/response models
  services/                   embedding_service, tokenizer_service
  jobs/                       job_runner, reflection_jobs
  utils/                      ids (ULID), time, text, errors
scripts/                      init_db, reset_db (rebuild chroma from sqlite), seed_demo_data
tests/                        conftest + fixtures; table-driven tests per module
```

Dependency direction: `api → engine → memory.repositories → memory.sqlite / memory.vector`.
FastAPI never touches SQLite/Chroma directly; domain models never import API schemas.

## 9. Explicitly OUT of V1

Chrome extension (V1 = copy-paste the Context Pack), dashboard, LLM classifier
strategies, backup/import/export, auth/security middleware, migrations tooling,
benchmarks, contradiction detection, LLM summarization, the Confidence *Engine*
(the field exists; the logic doesn't), multi-user support.

## 10. Build order

| Phase | Scope | Exit criterion |
|---|---|---|
| 0 | git init, uv env, deps, booting `/health` | Server starts, health returns 200 |
| 1 | Memory object, enums, SQLite schema, Chroma wrapper, embedding service | Round-trip: store → fetch → similarity query |
| 2 | Ingestion slice: `/ingest` → rules classifier → rubric scorer → router → store | Send messages, memories appear correctly classified |
| 3 | Retrieval + Context Pack: `/context` | **MVP proven** — paste pack into ChatGPT, it has memory |
| 4 | Working Memory Manager + sessions | Buffer survives restart |
| 5 | Reflection jobs (dedup, decay, state rebuild) | Duplicates merge automatically |
| 6 | Delta Context Builder | Second injection contains only new facts |

Every phase lands with pytest tests. Classifier/scorer use table-driven cases
("Thanks" → IGNORE, "We switched to FastAPI" → UPDATE).
