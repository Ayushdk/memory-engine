"""Local embeddings: sentence-transformers/all-MiniLM-L6-v2, 384-dim, CPU
(locked decision #4). Model loads lazily on first use (~2 s), never at import.
"""

from functools import lru_cache

from app.core.config import get_settings


class EmbeddingService:
    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or get_settings().embedding_model
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._load().encode(texts, normalize_embeddings=True).tolist()


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
