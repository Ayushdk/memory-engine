# OpenMemory Intelligence Layer — Design v2 (Frozen)

> **Status: FROZEN — v2 agreed 2026-07-10.** v2 extends the v1 freeze with
> the final product mandate: OpenMemory is a **local-first continuity
> engine**, not a memory database. It preserves long-term knowledge AND the
> user's current working context, so closing ChatGPT, opening Claude, and
> pressing Sync continues the work without re-explanation. Continuity is the
> success metric. Design changes reopen this document first, never code.
> Plugs into the V1 engine seams (architecture.md §1 #3, #6); V1 storage and
> transport decisions stand.

## Guiding principle: quality over quantity

OpenMemory does not optimize for remembering the most information possible;
it optimizes for preserving the information that genuinely improves future
reasoning and collaboration. **When in doubt, omit** — a missed memory costs
one re-explanation; a polluted knowledge base degrades every future pack,
reflection, and synthesis. This governs every extraction, reflection,
ranking, and synthesis decision below.

## 1. Locked design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Two evidence/knowledge layers**: episodic (raw turns) and semantic (extracted typed memories) | Evidence vs. knowledge; enables graceful degradation |
| 2 | **LLM proposes, deterministic code disposes** | LLM output is schema-validated, rule-checked, rejectable; a bad pass degrades to "nothing this pass", never corrupted state |
| 3 | **Ollama is the default provider**; no LLM → features no-op, engine keeps V1 heuristic behavior; cloud is explicit opt-in later | Local-first survives; intelligence is an enhancement, not a dependency |
| 4 | Intelligence work runs **async in background jobs**, never blocking chatting/ingest | Core latency insight, inherited from V1 #6 |
| 5 | Reflection is **fully autonomous** but **never destructively deletes** — merged/superseded/archived memories keep content, status, links | Auditable and reversible via the Dashboard |
| 6 | Project State is a **persisted, versioned generated document**; previous versions are never overwritten; latest = active overview | Fast sync, inspectable, project history for free |
| 7 | Memory relationships are **typed links** (`supersedes`, `relates_to`, `derived_from`), not a graph database | Graph queries + explainability at a fraction of the complexity |
| 8 | The Sync Context Pack is a **briefing, not a list**, composed deterministically under a token budget | Pack quality at 1000s of memories is won by clean layers, not sync-time cleverness |
| 9 | **Type existence rule**: a semantic type exists only if it has distinct semantics, lifecycle, retrieval behavior, or synthesis behavior | Prevents schema explosion |
| 10 | **Provenance is first-class**: every semantic memory links to the episode/turns that produced it; pruning **pins** referenced evidence | Explainability, debugging, confidence analysis |
| 11 | **Attributes are additive, never load-bearing**: per-type structured attributes enrich reflection/synthesis/dashboard; `content` prose stays self-contained | Degradation survives; a weak attribute never corrupts a memory |
| 12 | **Three knowledge layers**: Personal Brain (slow, reinforcement-gated), Project Brain (reflection-owned), Workspace (volatile working state) | Long-term knowledge and current working context are different problems solved by different stores |
| 13 | **Episodes are first-class entities** — conversations divide into episodes; the episode is the unit of summarization and extraction | Decisions emerge across exchanges; "the moment" needs a boundary to be captured at |
| 14 | **Dual summaries**: internal (engine-facing, larger, preserves) vs transfer (sync-facing, compact, for another LLM) | Two different consumers; conflating them ruins both |
| 15 | **Model roles**: light summarizer + heavy reasoner, independently configured; embeddings separate; never one model for every task | Summarization runs constantly and must be cheap; extraction/reflection need reasoning depth |
| 16 | **Dashboard (React + Vite) is the primary interface**; the extension stays intentionally minimal | The extension captures and syncs; understanding and managing knowledge needs a real application |

## 2. System overview

```
        conversation turns (extension → /ingest)      deterministic, never blocked
                     │
                     ▼
        ┌─────────────────────────┐
        │  EPISODIC BUFFER        │  raw turns per session (working memory)
        └───────────┬─────────────┘
     episode boundary: inactivity · message cap · tab close · Sync · switch
                     ▼
        ┌─────────────────────────┐
        │  EPISODE (first-class)  │──► SUMMARIZATION (summarizer model)
        └───────────┬─────────────┘         │
                     │                       ▼
                     │              ┌─────────────────────┐
                     │              │ WORKSPACE (volatile) │ internal + transfer
                     │              │ goal · blockers ·    │ summaries, updated
                     │              │ recent episodes      │ continuously
                     │              └─────────────────────┘
                     ▼
        SEMANTIC EXTRACTION (reasoner model, async)
                     ▼
        ┌─────────────────────────┐     ┌──────────────────────┐
        │  PROJECT BRAIN          │     │  PERSONAL BRAIN      │
        │  typed memories + links │     │  reinforcement-gated │
        └───────────┬─────────────┘     └──────────────────────┘
                     ▼
        REFLECTION (reasoner, async): consolidate · reconcile · promote ·
        archive · synthesize ──► PROJECT STATE (versioned)
                     ▼
        CONTEXT COMPOSITION (deterministic, budgeted) ──► Sync Context Pack
```

Every step is independently replaceable (module functions behind stable
signatures; only the LLM provider is a formal interface, §9).

## 3. The three knowledge layers

### 3.1 Personal Brain — long-term user knowledge
Preferences, skills, goals, writing style, permanent facts, interests.
Changes slowly by design. Storage: the existing PROFILE view. **Promotion is
gated**: reinforcement count, confidence, importance, and explicit intent
("remember that I…") decide promotion; single mentions do not. Reflection
executes promotions.

### 3.2 Project Brain — long-term project knowledge
Architecture, decisions, constraints, facts, insights, ideas, open
questions, project state. **Reflection owns this layer.** Live conversations
never write it directly — only the async extraction/reflection pipeline
does, through the repository gate.

### 3.3 Workspace — current working context (NOT a memory database)
Three related but distinct artifacts, one project each:

- **Workspace Timeline** — chronological episode history (the `episodes`
  table; nothing extra stored, derived on read via `GET /episodes`).
- **Workspace State** — current understanding of the work: internal summary
  (preserves detail, working-notes style, not conversational narration),
  goal, blockers. Grows by merging each closed episode's summary in.
- **Transfer Summary** — compact briefing optimized for AI handoff. Budgeted
  by `transfer_summary_token_budget` (not a sentence count) and re-trimmed
  after every update regardless of what the model returns. This is the field
  that leads the Sync Context Pack.

Updates continuously as episodes close. Reset or archived by the user; never
permanent. Workspace is what makes Sync feel like continuing, not being
reminded.

## 4. Episodes

One conversation contains multiple episodes. Boundaries (deterministic):
inactivity timeout, message count cap, tab close, Sync click, conversation
switch. Each episode is summarized (summarizer model; heuristic
selection/truncation fallback) and becomes the source for workspace updates,
semantic extraction, reflection, and project-state generation. Episodes
referenced by active memories are **pinned** — never pruned (decision #10).

## 5. Semantic memory model (Project/Personal Brain entries)

A **self-contained, typed unit of durable knowledge**: readable in
isolation, months later, without the source conversation.

**Type existence rule (decision #9)** governs the taxonomy. `reasoning` and
`tradeoff` are content requirements and attributes, not types; `idea` is a
type (unique promotion path).

| Type | Captures | Example |
|---|---|---|
| `decision` | choice + alternatives + why rejected + rationale | "Chose SQLite over Postgres: local-first, zero-ops, rebuildable index" |
| `constraint` | must / must-not | "No cloud calls; all data stays on the machine" |
| `fact` | stable truth about project or user | "Engine is FastAPI on 127.0.0.1:8000" |
| `preference` | how the user works | "Small steps, tests per step, review before next" |
| `insight` | reasoning or trade-off worth keeping | "Claude DOM has no message ids → content-based dedupe" |
| `open_question` | unresolved thread | "Cross-session duplicates not collapsed at 0.85" |
| `idea` | deliberately deferred proposal + revisit trigger | "Dashboard deferred until extension proves the flow" |

**Decision content contract:** choice, alternatives considered, why they
lost, rationale — a decision without its why is half a memory (fixture-
enforced extraction requirement).

**Fields:** `content` (canonical prose) · type · status
(`active|superseded|archived|merged`) · links (typed, via
`memory_relations`) · `attributes` (optional per-type JSON; first contract:
decision `{rationale, alternatives:[{option, why_rejected}], consequences}`;
empty in heuristic mode; new attributes need no migration) · provenance
(platform, session, **episode id + turn range**, extractor model + prompt
version) · confidence (top-level, V1 #7).

**Lifecycle:** created → reinforced (same knowledge re-extracted bumps
confidence/recency, no duplicate) → superseded (content kept, `superseded_by`
link — "why we changed our minds" is context) → archived. `idea` adds the
only promotion path: idea → decision (`derived_from` link) | rejected (with
the why) | stale.

## 6. Extraction

Runs async on episode close, **after** the Workspace State update — over the
Workspace's distilled `internal_summary`, not the raw episode transcript.
The episode is evidence (provenance via `Source.episode_id`), the Workspace
is the continuously maintained understanding, and extraction evolves the
Project Brain from that understanding rather than repeatedly reinterpreting
raw conversation. Reasoner model, JSON-schema output, **empty-list bias**:
"return nothing unless something durable and self-contained happened" —
every extracted memory must stand alone, readable months later without the
source conversation; uncertainty means no memory, not a weak one.
Deterministic gate in the repository: embedding similarity shortlists
existing near-matches → reinforce (recency + confidence bump) instead of
insert. Dogfooding examples (should-have / shouldn't-have stored) are the fixture
suite.

Extraction currently re-reads the entire `internal_summary` on every episode
close, not just what changed since the last extraction. This is intentional:
simple and deterministic, and easy to validate during dogfooding. Incremental
extraction (diffing against a last-extracted watermark) is a future
optimization, not a correctness gap — the reinforcement gate already absorbs
repeated re-surfacing of the same facts. Do not redesign this without a
concrete cost or quality problem observed in practice.

## 7. Reflection

Async job (episode close + every N new memories). Autonomous; never
hard-deletes. Jobs: **consolidate** (merge near-duplicates the write-time
check missed), **reconcile** (supersession/contradiction), **promote**
(repeated observations → stable memories; adopted ideas → decisions;
reinforced personal facts → Personal Brain), **archive** (stale,
low-confidence), **synthesize** (regenerate Project State), **update links**.

## 8. Project State & the Sync Context Pack

**Project State**: generated by reflection from active Project Brain
memories + workspace; versioned rows, never overwritten; latest version is
the active project overview; inputs recorded (explainable).

**Pack composition** (deterministic, budgeted, renderer contract from M2
unchanged — pack precedes the user's draft):

1. **Project state** — the "you are here"
2. **Active decisions & constraints** — ranked by type priority, confidence, recency
3. **Preferences** — Personal Brain: how to work with this user
4. **Transfer summary** — the workspace's compact "the moment": current goal, blockers, recent thread
5. **Open questions & deferred ideas** — ranked below active guidance; budget headroom only

## 9. Models & validation

One formal interface: `LLMProvider.generate(prompt, output_schema) ->
validated dict` + `health()`. Roles (`create_provider(role)`):

| Role | Default | Used by |
|---|---|---|
| summarizer | `qwen2.5:3b` (candidate `gemma3:4b`) | episode summaries, workspace updates, transfer summary |
| reasoner | `qwen3:8b` | extraction, reflection, project-state synthesis |

Embeddings stay independent (MiniLM). Validation pipeline everywhere —
**never trust model output**: LLM → JSON → jsonschema → business-rule
validation → repository → storage. Only `summarize`/`extract`/`reflect`/
`synthesize_state` ever hold a provider; repositories and composers are pure
deterministic code. Provider absent → those functions no-op; everything else
runs unchanged.

**Background jobs**: lightweight in-process asyncio workers started in the
app lifespan. No Redis/Celery — this is a local-first application.
Single-writer discipline: all job writes go through repositories.

**Managed deployment**: Ollama is an internal dependency run by Docker
Compose (`docker-compose.yml`), not a manual install. The **engine
provisions its own models** — at startup it pulls missing role models via
Ollama's `/api/pull` (`model_manager.py`); `/health` reports pull progress.
Compose stays dumb; provisioning is deployment-agnostic (works for native
installs and the future OpenMemory CLI too). `idea`: containerize the engine
into the same compose file at the distribution phase, giving end users the
whole stack from one `docker compose up -d`; deferred because the torch
image is heavy and slows the dev loop while the product is single-user.

## 10. Clients

**Extension (intentionally minimal):** connected status, current project,
platform, Sync Context, Capture ON/OFF, Reset Workspace, Archive Workspace,
Dashboard link, Settings. Nothing more.

**Dashboard (React + Vite, primary interface):** per project — Overview
(project state, current objective, next suggested task, recent decisions,
active workspace) · Workspace (summary, goal, blockers, episode history,
sync/archive/reset) · Project Brain (categorized memories) · Timeline
(historical evolution) · Generate Context (preview/generate prompts) ·
Settings.

## 11. Implementation plan (agreed 2026-07-10)

Dependency-ordered phases; each leaves the repo working, is independently
reviewable (architecture explanation, summary, trade-offs, risks, tests),
and is committed after review.

0. **Cleanup + LLM infra** — delete dead scaffolding, this doc v2,
   provider roles, commit. Gate: Ollama installed, models pulled,
   `scripts/llm_spotcheck.py` judged per candidate.
1. **Episodes + job runner** — episodes table/repository, additive
   `PRAGMA user_version` migrations, deterministic boundaries, asyncio job
   runner, summarization job with heuristic fallback.
2. **Workspace** — workspace store + update loop, dual summaries,
   reset/archive API, transfer summary leads the sync pack (continuity win
   before extraction exists), minimal extension controls.
3. **Extraction → Project Brain** — type/attribute/provenance schema,
   typed links, `extract()` + reinforce/insert gate, typed pack sections,
   fixture suite. V1 rule-ingest stays as no-LLM fallback.
4. **Reflection + Project State** — consolidate/reconcile/promote/archive,
   versioned project states.
5. **Pack composition v2 + Personal Brain promotion** — full budgeted
   briefing; reinforcement-gated PROFILE promotion.
6. **Dashboard** — React+Vite app served by the engine; supporting API
   endpoints (projects, episodes, workspace, state versions, browse/search,
   pack preview).

## 12. Open questions to answer with real usage

1. Do 3–4B models clear the summarization bar; does `qwen3:8b` clear the
   extraction bar (spot-check + dogfooding)?
2. Episode boundary tuning (inactivity minutes, message cap).
3. Pack token budget default per target assistant.
4. Attribute fill quality: reasoner-only, or gate to larger models?
5. Episodic retention horizon (beyond pinned evidence).
