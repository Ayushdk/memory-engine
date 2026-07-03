"""Phase 1 exit criterion: store → fetch → similarity query (architecture.md §10).

Uses the real MiniLM model and a real embedded Chroma instance.
"""

from tests.conftest import make_memory

from app.memory.repositories.memory_repository import MemoryRepository
from app.models.enums import MemoryCategory, MemoryView


def test_store_fetch_similarity_query(db_conn, vector_store, embedding_service):
    repo = MemoryRepository(db_conn)

    backend = make_memory(content="Selected FastAPI over Flask for the backend.")
    coffee = make_memory(
        content="User drinks two espressos every morning.",
        category=MemoryCategory.PREFERENCE,
        view=MemoryView.PROFILE,
        project_id=None,
        importance=4,
    )
    for memory in (backend, coffee):
        repo.save(memory)  # SQLite first (source of truth) ...
        vector_store.upsert(memory, embedding_service.embed(memory.content))  # ... Chroma second

    # Fetch from the source of truth
    assert repo.get(backend.id).content == backend.content

    # Similarity query: the web-framework question must rank the backend memory first
    query_embedding = embedding_service.embed("Which web framework did we choose?")
    results = vector_store.query(query_embedding, n_results=2)
    assert results[0][0] == backend.id
    assert results[0][1] > results[1][1]

    # Metadata pre-filtering: profile view only returns the coffee memory
    filtered = vector_store.query(query_embedding, n_results=2, where={"view": "profile"})
    assert [mid for mid, _ in filtered] == [coffee.id]


def test_delete_removes_from_index(db_conn, vector_store, embedding_service):
    repo = MemoryRepository(db_conn)
    memory = make_memory()
    repo.save(memory)
    vector_store.upsert(memory, embedding_service.embed(memory.content))

    repo.delete(memory.id)
    vector_store.delete(memory.id)
    assert vector_store.count() == 0
