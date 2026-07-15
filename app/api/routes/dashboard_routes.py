"""Dashboard routes: read-only projections over existing engine state."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import (
    get_conversation_summary_repository,
    get_episode_repository,
    get_memory_repository,
    get_project_repository,
    get_project_state_repository,
    get_raw_message_repository,
    get_workspace_repository,
)
from app.core.config import get_settings
from app.memory.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.memory.repositories.episode_repository import EpisodeRepository
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.repositories.project_repository import ProjectRepository
from app.memory.repositories.project_state_repository import ProjectStateRepository
from app.memory.repositories.raw_message_repository import RawMessageRepository
from app.memory.repositories.workspace_repository import WorkspaceRepository
from app.models.enums import MemoryStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _conn(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def _count(conn: sqlite3.Connection, table: str, where: str = "", args: tuple = ()) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table} {where}", args).fetchone()
    return int(row[0] if row else 0)


def _latest_summary(conn: sqlite3.Connection, session_id: str | None = None) -> dict | None:
    if session_id:
        row = conn.execute(
            "SELECT session_id, summary, updated_at FROM conversation_summaries "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT session_id, summary, updated_at FROM conversation_summaries "
            "WHERE summary != '' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


@router.get("/overview")
async def overview(
    request: Request,
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    episodes: Annotated[EpisodeRepository, Depends(get_episode_repository)],
) -> dict:
    conn = _conn(request)
    latest_session = conn.execute(
        "SELECT id, platform, project_id, last_activity_at, started_at FROM sessions "
        "ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 1"
    ).fetchone()
    latest_summary = _latest_summary(conn)
    last_sync = conn.execute("SELECT MAX(injected_at) FROM injections").fetchone()
    active_projects = projects.list()
    open_episodes = [e for e in episodes.list(limit=200) if e.status == "open"]
    settings = get_settings()
    return {
        "engine_status": "ok",
        "current_platform": latest_session["platform"] if latest_session else None,
        "current_session": latest_session["id"] if latest_session else None,
        "current_project": latest_session["project_id"] if latest_session else None,
        "memory_capture_status": "active" if open_episodes else "idle",
        "last_sync": last_sync[0] if last_sync else None,
        "conversation_summary_status": "ready" if latest_summary else "empty",
        "conversation_summary_updated_at": latest_summary["updated_at"] if latest_summary else None,
        "total_projects": len(active_projects),
        "total_memories": _count(conn, "memories", "WHERE status = ?", (MemoryStatus.ACTIVE.value,)),
        "total_conversations": _count(conn, "sessions"),
        "database_health": "ok",
        "embedding_model": settings.embedding_model,
        "llm_model": settings.ollama_summarizer_model if settings.llm_provider == "ollama" else "none",
    }


@router.get("/current-context")
def current_context(
    request: Request,
    session_id: Annotated[str | None, Query()] = None,
) -> dict:
    summary = _latest_summary(_conn(request), session_id=session_id)
    text = summary["summary"] if summary else ""
    return {
        "session_id": summary["session_id"] if summary else session_id,
        "conversation_summary": text,
        "last_updated": summary["updated_at"] if summary else None,
        "word_count": len(text.split()),
        "character_count": len(text),
    }


@router.get("/projects")
def project_dashboard(
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    memories: Annotated[MemoryRepository, Depends(get_memory_repository)],
    episodes: Annotated[EpisodeRepository, Depends(get_episode_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    project_states: Annotated[ProjectStateRepository, Depends(get_project_state_repository)],
) -> list[dict]:
    rows = []
    for project in projects.list():
        workspace = workspaces.get(project.id)
        state = project_states.latest(project.id)
        project_memories = memories.list(project_id=project.id, status=MemoryStatus.ACTIVE, limit=8)
        rows.append(
            {
                "project": project,
                "workspace_summary": workspace.transfer_summary or workspace.internal_summary,
                "project_brain": state.content if state else "",
                "recent_conversations": episodes.list(project_id=project.id, limit=5),
                "important_memories": sorted(
                    project_memories, key=lambda m: (m.importance, m.updated_at), reverse=True
                )[:5],
                "last_updated": max(
                    [
                        project.updated_at,
                        workspace.updated_at,
                        *(m.updated_at for m in project_memories),
                    ]
                ).isoformat(),
            }
        )
    return rows


@router.get("/search")
def search(
    request: Request,
    q: Annotated[str, Query(min_length=1)],
    project_id: Annotated[str | None, Query()] = None,
) -> dict:
    conn = _conn(request)
    like = f"%{q}%"
    project_clause = "AND project_id = ?" if project_id else ""
    project_args = (project_id,) if project_id else ()
    return {
        "conversation_summaries": [
            dict(r)
            for r in conn.execute(
                "SELECT session_id, summary, updated_at FROM conversation_summaries "
                "WHERE summary LIKE ? ORDER BY updated_at DESC LIMIT 25",
                (like,),
            ).fetchall()
        ],
        "workspaces": [
            dict(r)
            for r in conn.execute(
                "SELECT project_id, transfer_summary, internal_summary, updated_at FROM workspaces "
                f"WHERE (transfer_summary LIKE ? OR internal_summary LIKE ?) {project_clause} "
                "ORDER BY updated_at DESC LIMIT 25",
                (like, like, *project_args),
            ).fetchall()
        ],
        "memories": [
            dict(r)
            for r in conn.execute(
                "SELECT id, content, summary, category, view, project_id, updated_at FROM memories "
                f"WHERE status = 'active' AND (content LIKE ? OR COALESCE(summary, '') LIKE ?) {project_clause} "
                "ORDER BY updated_at DESC LIMIT 50",
                (like, like, *project_args),
            ).fetchall()
        ],
        "projects": [
            dict(r)
            for r in conn.execute(
                "SELECT id, name, status, updated_at FROM projects "
                "WHERE id LIKE ? OR name LIKE ? ORDER BY updated_at DESC LIMIT 25",
                (like, like),
            ).fetchall()
        ],
    }


@router.get("/diagnostics")
def diagnostics(
    request: Request,
    raw_messages: Annotated[RawMessageRepository, Depends(get_raw_message_repository)],
    conversation_summaries: Annotated[
        ConversationSummaryRepository, Depends(get_conversation_summary_repository)
    ],
) -> dict:
    conn = _conn(request)
    settings = get_settings()
    recent_errors: list[str] = []
    latest_raw_message = raw_messages.conn.execute(
        "SELECT session_id, timestamp FROM raw_messages ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    latest_summary = conversation_summaries.latest(datetime.min)
    return {
        "engine_status": "ok",
        "database_status": "ok",
        "embedding_model": settings.embedding_model,
        "llm_model": {
            "provider": settings.llm_provider,
            "summarizer": settings.ollama_summarizer_model if settings.llm_provider == "ollama" else "none",
            "reasoner": settings.ollama_reasoner_model if settings.llm_provider == "ollama" else "none",
        },
        "raw_messages_count": _count(conn, "raw_messages"),
        "episode_count": _count(conn, "episodes"),
        "conversation_summary_count": _count(conn, "conversation_summaries", "WHERE summary != ''"),
        "workspace_count": _count(conn, "workspaces"),
        "memory_count": _count(conn, "memories", "WHERE status = ?", (MemoryStatus.ACTIVE.value,)),
        "processing_statistics": {
            "unsummarized_messages": _count(conn, "raw_messages", "WHERE summarized = 0"),
            "open_episodes": _count(conn, "episodes", "WHERE status = 'open'"),
            "closed_episodes": _count(conn, "episodes", "WHERE status = 'closed'"),
            "summarized_episodes": _count(conn, "episodes", "WHERE status = 'summarized'"),
        },
        "errors": recent_errors,
        "recent_logs": [],
        "latest_raw_message": dict(latest_raw_message) if latest_raw_message else None,
        "latest_conversation_summary": latest_summary,
    }


@router.get("/settings")
def settings() -> dict:
    s = get_settings()
    return {
        "engine": {
            "ollama_url": s.ollama_url,
            "active_models": {
                "embedding": s.embedding_model,
                "summarizer": s.ollama_summarizer_model if s.llm_provider == "ollama" else "none",
                "reasoner": s.ollama_reasoner_model if s.llm_provider == "ollama" else "none",
            },
            "token_budgets": {
                "context": s.context_token_budget,
                "conversation_summary": s.conversation_summary_token_budget,
                "workspace": s.transfer_summary_token_budget,
            },
            "capture_settings": {
                "episode_max_messages": s.episode_max_messages,
                "episode_inactivity_minutes": s.episode_inactivity_minutes,
            },
            "sync_settings": {
                "retrieval_candidates": s.retrieval_candidates,
                "retrieval_top_k": s.retrieval_top_k,
                "recap_freshness_minutes": s.recap_freshness_minutes,
            },
        },
        "extension": {
            "pause_capture": "managed in extension storage",
            "export": "not configured",
            "import": "not configured",
            "reset": "not configured",
        },
    }
