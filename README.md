# OpenMemory Engine

Local-first memory engine for AI conversations — the brain of OpenMemory OS.

Everything else (browser extension, dashboard, FastAPI transport) is a **client**
of the Memory Engine in `app/engine/`. The engine is importable and testable
without starting a web server.

**The full V1 specification is frozen in [docs/architecture.md](docs/architecture.md).**
Read that before touching any code.

## Core ideas

- **Unified memory store** — one `memories` table + one Chroma collection.
  Memory types (working / profile / project / episodic / semantic) are logical
  views over metadata, like Gmail labels — never separate databases.
- **Three paths, three latency budgets** — ingestion (sync, <100 ms, no LLM),
  retrieval (sync, <500 ms), reflection (async background, unbounded).
- **Free and offline by default** — SQLite + embedded ChromaDB + local
  `all-MiniLM-L6-v2` embeddings. Classifier and scorer are rules-based in V1,
  swappable for LLM strategies (Ollama / Gemini) behind the same interface.

## Pipeline

```
Incoming Message → Working Memory → Classifier → Scorer → Router → Unified Store
                                                                        │
                              Reflection (async): dedup → consolidation → Project State
                                                                        │
User Query → Retrieval → Context Builder → Delta Builder → Context Pack → LLM
```

## Stack

Python 3.11+ · FastAPI · SQLite · ChromaDB · Pydantic · sentence-transformers · loguru · pytest · uv

## Status

Architecture frozen; implementation starting at Phase 0 (see build order in
[docs/architecture.md](docs/architecture.md) §10).
