import os

# Tests must not inherit the developer's .env (auth token, live Ollama).
# Env vars beat the dotenv file; set before any app.core.config import.
os.environ["OPENMEMORY_API_TOKEN"] = ""
os.environ["OPENMEMORY_LLM_PROVIDER"] = "none"
os.environ["OPENMEMORY_EMBEDDING_MODEL"] = "sentence-transformers/all-MiniLM-L6-v2"

import pytest

from app.memory.sqlite.connection import create_connection
from app.memory.vector.chroma_client import ChromaVectorStore
from app.models.domain.memory import Memory
from app.models.enums import Confidence, MemoryCategory, MemoryView
from app.services.embedding_service import EmbeddingService


@pytest.fixture
def db_conn(tmp_path):
    conn = create_connection(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def vector_store(tmp_path):
    return ChromaVectorStore(persist_dir=tmp_path / "chroma")


@pytest.fixture(scope="session")
def embedding_service():
    # Session-scoped: loading MiniLM takes seconds, embedding takes milliseconds.
    return EmbeddingService()


def make_memory(**overrides) -> Memory:
    defaults = dict(
        content="Selected FastAPI over Flask for the backend.",
        summary="Backend = FastAPI",
        category=MemoryCategory.DECISION,
        view=MemoryView.PROJECT,
        project_id="proj_openmemory",
        importance=9,
        confidence=Confidence.HIGH,
        tags=["backend", "architecture"],
    )
    return Memory(**{**defaults, **overrides})
