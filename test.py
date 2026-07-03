from app.memory.sqlite.connection import create_connection
from app.memory.repositories.memory_repository import MemoryRepository
from app.memory.vector.chroma_client import ChromaVectorStore

MEMORY_ID = "mem_01KWMJ5CNZB1BSC8Q9B77DBWQ5"

conn = create_connection()

repo = MemoryRepository(conn)
vector_store = ChromaVectorStore()

print(repo.delete(MEMORY_ID))
vector_store.delete(MEMORY_ID)

print("Remaining SQLite:", len(repo.list(status=None)))
print("Remaining Chroma:", vector_store.count())

conn.close()