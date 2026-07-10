# OpenMemory Intelligence Layer — Design (Frozen)

> **Status: FROZEN — design agreed 2026-07-10.** Dogfooding (§10) validates
> or challenges this design before implementation begins; a challenge reopens
> the relevant section here first, never in code. This layer plugs into the
> seams the V1 architecture reserved for it (architecture.md §1 decisions #3
> and #6). It changes no V1 storage or transport decisions.

## Guiding principle: quality over quantity

OpenMemory does not optimize for remembering the most information possible;
it optimizes for preserving the information that genuinely improves future
reasoning and collaboration. **When in doubt, omit** — a missed memory costs
one re-explanation; a polluted knowledge base degrades every future pack,
reflection, and synthesis. This principle governs every extraction,
reflection, ranking, and synthesis decision below.

---

## 0. Why this layer exists

M1/M2 built storage, retrieval, sync, and clients. The gap to the product
vision — a universal, local-first memory OS for AI — is no longer
infrastructure; it is intelligence. Today the engine stores lightly-summarized
messages. The vision requires it to store *durable knowledge*: decisions,
constraints, reasoning, preferences, project state. Extraction, consolidation,
project understanding, and pack composition are one subsystem, designed here
together.

## 1. Locked design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Two memory layers**: episodic (raw turns, today's pipeline) and semantic (extracted typed memories) | Evidence vs. knowledge. Nothing built in M1/M2 is wasted — it becomes the episodic layer. Enables graceful degradation |
| 2 | **LLM proposes, deterministic code disposes** | LLM output is schema-validated, provenance-stamped, rejectable. A bad extraction degrades to "nothing extracted", never corrupted state |
| 3 | **Ollama + small local model is the default provider**; no LLM configured → system degrades to today's heuristic behavior; cloud providers are explicit opt-in later | Local-first survives; intelligence is an enhancement, not a dependency |
| 4 | Extraction runs **incrementally on conversation-quiet + a session-end sweep**, async, never blocking ingest | Memories are fresh even mid-session; mirrors the extension observer's debounce pattern |
| 5 | Reflection is **fully autonomous** (merge, supersede) but **never destructively deletes** — merged/superseded memories keep content, status, and links | Every action auditable and reversible via the future dashboard |
| 6 | Project state is a **persisted, versioned generated document** per project, written by reflection, read by sync | Fast sync, inspectable, project history for free |
| 7 | Memory relationships are **typed links on memories** (`supersedes`, `relates_to`, `derived_from`), not a graph database | Gives graph queries + explainability at a fraction of the complexity |
| 8 | The Sync Context Pack is a **briefing, not a list**, composed deterministically under a token budget | Pack quality at 1000s of memories is won by reflection keeping the semantic layer clean, not by sync-time cleverness |
| 9 | **Type existence rule**: a semantic type exists only if it has distinct semantics, lifecycle, retrieval behavior, or synthesis behavior; everything else is content or an attribute | Prevents schema explosion; gives future "should this be a type?" debates a test |
| 10 | **Provenance is first-class**: every semantic memory links to the episodic turns that produced it, and episodic pruning **pins** (never deletes) turns referenced by active memories | Explainability, debugging, confidence analysis; the evidence chain stays walkable forever |
| 11 | **Attributes are additive, never load-bearing**: per-type structured attributes (e.g. a decision's alternatives) enrich reflection/synthesis/dashboard, but `content` prose must remain self-contained without them | Degradation ladder survives (heuristic mode fills no attributes); a small model's weak attribute never corrupts the memory's usefulness |

## 2. Pipeline overview

```
 conversation turns (extension → /ingest)          ← unchanged, deterministic
        │
        ▼
 ┌─────────────────┐
 │ EPISODIC LAYER  │  raw turns; exact; short retention; the evidence
 └────────┬────────┘
          │ async, conversation-quiet + session-end sweep
          ▼
 ┌─────────────────┐   LLM: window → candidate memories (JSON schema)
 │   EXTRACTION    │   deterministic: validate, provenance-stamp, dedupe
 └────────┬────────┘   shortlist via embedding similarity
          ▼
 ┌─────────────────┐
 │ SEMANTIC LAYER  │  typed memories with lifecycle + links
 └────────┬────────┘
          │ background (session-end / every N new memories)
          ▼
 ┌─────────────────┐   consolidate · reconcile · promote ·
 │   REFLECTION    │   synthesize project-state document
 └────────┬────────┘
          ▼
 ┌─────────────────┐   deterministic: rank, budget, render
 │ SYNC COMPOSER   │   project state → decisions/constraints →
 └─────────────────┘   preferences → recent thread → open questions
```

## 3. What is a memory?

A **self-contained, typed unit of durable knowledge**. Quality bar: readable
in isolation, months later, without the source conversation, and still true —
or explicitly marked no longer true.

### 3.1 Types (small on purpose; each must earn its place in the pack)

**Type existence rule (locked decision #9):** a type exists only if it has
distinct semantics, lifecycle, retrieval behavior, or synthesis behavior.
By this rule, `reasoning` and `tradeoff` are *not* types — they are content
requirements and attributes (§3.2) — while `idea` is.

| Type | Captures | Example |
|---|---|---|
| `decision` | choice + rejected alternatives + rationale | "Chose SQLite over Postgres: local-first, zero-ops, Chroma index is rebuildable" |
| `constraint` | must / must-not | "No cloud calls; all data stays on the machine" |
| `fact` | stable truth about project or user | "Engine is FastAPI on 127.0.0.1:8000" |
| `preference` | how the user works | "Small steps, tests per step, review before the next" |
| `insight` | reasoning or trade-off worth keeping | "Claude DOM has no message ids → dedupe must be content-based" |
| `open_question` | unresolved thread / next step | "Cross-session duplicate memories not collapsed by the 0.85 threshold" |
| `idea` | proposal deliberately deferred: the idea, why deferred, revisit trigger | "Toolbar PNG icons deferred — no image tooling; revisit at M3 polish" |

`idea` is distinct from `open_question`: an open question is unresolved and
needs an answer; an idea is *resolved for now* ("considered, not yet"). It is
the only type with a promotion path (§3.3), and it exists so a fresh
assistant never re-proposes something already considered and shelved.

**Decision content contract:** a `decision` must capture the choice, the
alternatives considered, why they were rejected, and the rationale — a
decision without its *why* is half a memory. This is an extraction
requirement enforced by fixtures, and (per rule #9) the reason `tradeoff`
needs no type of its own: resolved trade-offs live inside decisions,
unresolved ones are `insight` or `open_question`. Project state is not a
memory type at all (§6).

### 3.2 Fields

Existing unified store (architecture.md §1 #2) plus:

- `content` — self-contained prose; **always the canonical form** (rule #11)
- `type` — one of §3.1
- `status` — `active` | `superseded` | `archived`
- `links` — `[{kind: supersedes|relates_to|derived_from, target: <memory id>}]`
- `attributes` — optional per-type structured JSON, filled by the extractor
  when an LLM is available, empty in heuristic mode. First contract, for
  `decision`: `{rationale, alternatives: [{option, why_rejected}],
  consequences}`. Consumed by reflection, project-state synthesis, and the
  dashboard; the pack renders from `content`. New attributes need no
  migration. (`confidence` stays a top-level field per V1 decision #7 — not
  duplicated here.)
- `provenance` — platform, session id, **references to the episodic turns
  that produced the memory** (turn range/ids), extractor model + prompt
  version. First-class (rule #10): the memory → turns → session chain must
  stay walkable, so episodic pruning **pins** turns referenced by active
  memories instead of deleting them. Referenced turns are a small fraction of
  the episodic layer, so pinning is cheap.

### 3.3 Lifecycle (deterministic state machine)

- **created** → **reinforced**: same knowledge re-extracted → bump
  confidence/recency, no duplicate row
- → **superseded**: contradicted by a newer memory → keep content, flip
  status, add `superseded_by` link ("why did we change our minds?" is itself
  context)
- → **archived**: stale / low-confidence / user-removed. Excluded from packs,
  kept for audit. The system never hard-deletes.

`idea` additionally has the only **promotion path**:

- **idea → decision**: the idea is adopted → a new `decision` memory is
  created with a `derived_from` link back; the idea flips to superseded.
- **idea → rejected**: explicitly turned down → superseded, with the why.
- **idea → stale**: never revisited → archived by reflection over time.

## 4. Extraction

- **Windows, not messages; many-to-many.** Decisions emerge across exchanges;
  extraction reads the new episodic tail plus enough prior context to resolve
  references, and emits zero or more candidates.
- **Bias against storing.** The prompt contract: "return an empty list unless
  something durable happened." Most conversation is ephemeral.
- **Deterministic gate:** every candidate is schema-validated; embedding
  similarity shortlists existing near-matches → reinforce instead of insert.
- Dogfooding examples (should-have-stored / should-not-have-stored) become
  the extractor's fixture suite before any implementation.

## 5. Reflection

Background pass, session-end or every N new memories. Four jobs:

1. **Consolidate** — merge near-duplicates the write-time check missed
   (root-cause fix for the observed "SQLite decision ×3"; the 0.85 write-time
   threshold stays as a cheap pre-filter only).
2. **Reconcile** — detect supersession/contradiction among active memories
   (LLM confirms; state machine executes).
3. **Promote** — repeated observations → stable `preference`/`fact` with
   raised confidence; adopted `idea` → `decision` (§3.3 promotion path).
4. **Synthesize** — regenerate the project-state document (§6).

## 6. Project state

A generated, versioned document per project — a living README the system
writes: what the project is, current architecture, active constraints, where
work stands, open threads. Regenerated by reflection from active memories +
the recent episodic tail; inputs recorded (explainable); prior versions kept
(project history). Sync reads it; it never blocks or invokes the LLM at sync
time.

## 7. The Sync Context Pack

Composed deterministically under an explicit token budget:

1. **Project state** — the "you are here"
2. **Active decisions & constraints** — ranked by type priority, confidence,
   recency
3. **Preferences** — how to work with this user
4. **Recent thread** — short episodic recap of the last session (the *moment*,
   not just the project)
5. **Open questions & deferred ideas** — often exactly why the user opened a
   new assistant; `idea` memories rank below active guidance and appear only
   under budget headroom, so a fresh assistant doesn't re-propose what was
   already shelved

Ranking/budgeting is pure code. Renderer contract from M2 (pack precedes the
user's draft, ends with "the user's message follows") is unchanged.

## 8. LLMProvider interface

One internal interface; all intelligence features call through it.

```
LLMProvider.generate(prompt, output_schema) -> validated dict | ProviderError
```

- Default: Ollama, small local model (3–8B class). Extraction/consolidation
  are *constrained* tasks — classify, summarize into a schema, compare two
  texts — within small-model competence.
- Provider unset/unreachable → features no-op cleanly; engine behaves as
  today (episodic capture + heuristic recap). Health endpoint reports
  intelligence status so clients can show it.
- Cloud providers (Gemini, Claude API) later, behind the same interface,
  explicit opt-in only.

### Division of labor

| LLM (proposes) | Deterministic (disposes) |
|---|---|
| extraction (window → candidates) | ingest, storage, embeddings |
| merge confirmation | similarity shortlisting |
| contradiction detection | lifecycle state machine |
| project-state synthesis | ranking, budgeting, rendering, API |

## 9. Explicitly out of scope (this phase)

- Graph database / triple store (typed links suffice until proven otherwise)
- Cloud LLM providers (interface reserves the slot)
- Dashboard UI for the audit trail (M3; the data model supports it now)
- IDE clients (Cursor/VS Code) — they reuse the same API when they come
- Any implementation before dogfooding validates this design

## 10. Dogfooding validation checklist

Collect during daily use; each example either confirms the design or forces a
revision *here* before code:

- [ ] memories that **should** have been stored (→ extractor fixtures)
- [ ] memories that should **not** have been stored (→ extractor fixtures)
- [ ] missing context at sync time (→ pack composition §7)
- [ ] duplicate memories (→ consolidation §5)
- [ ] poor sync packs (→ ranking/budget §7, project state §6)
- [ ] moments where "the moment" was lost even though "the project" synced
      (→ recent-thread section §7.4)

Open questions to answer with data before implementation:

1. Which local model actually clears the extraction quality bar on the
   user's hardware (candidate sizes: 3B vs 8B; latency vs quality)?
2. Episodic retention horizon (how far back does extraction ever need?)
3. Token budget default for the pack (what do target assistants handle well?)
4. Reflection trigger tuning (session-end only vs every-N in practice)
5. Attribute fill quality: can the chosen local model populate the
   `decision` attributes contract reliably, or should attributes start
   LLM-tier-gated (filled only by larger/cloud models)?
