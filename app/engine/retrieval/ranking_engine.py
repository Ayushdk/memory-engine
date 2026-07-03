"""Ranking Engine (architecture.md §4): re-ranks retrieval candidates with

    score = 0.45·cosine + 0.25·importance + 0.20·recency + 0.10·access_freq

Every signal is normalized to [0,1] before weighting. Pure function of the
RetrievalResult — no storage, no embeddings, no side effects — so BM25/ML/LLM
rerankers can replace it without touching the retrieval pipeline.
"""

import math
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.models.domain.memory import Memory
from app.engine.retrieval.retrieval_engine import RetrievalResult
from app.utils.time import utc_now

WEIGHTS = {"similarity": 0.45, "importance": 0.25, "recency": 0.20, "access_frequency": 0.10}

# ponytail: fixed 30-day half-life for recency decay; promote to Settings if
# tuning ever becomes necessary.
RECENCY_HALF_LIFE_DAYS = 30.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class RankingResult:
    ranked_memories: list[Memory]
    ranking_scores: dict[str, float]  # memory id → final weighted score
    selected_memory_ids: list[str]
    ranking_metadata: dict = field(default_factory=dict)


class RankingEngine:
    def rank(
        self,
        retrieval: RetrievalResult,
        project_id: str | None = None,  # reserved for future rerankers; unused by V1 formula
        top_k: int | None = None,
    ) -> RankingResult:
        top_k = top_k or get_settings().retrieval_top_k
        similarities: dict[str, float] = retrieval.retrieval_metadata.get("similarities", {})
        now = utc_now()

        max_access = max((m.access_count for m in retrieval.retrieved_memories), default=0)

        components: dict[str, dict[str, float]] = {}
        scores: dict[str, float] = {}
        for memory in retrieval.retrieved_memories:
            age_days = (now - memory.updated_at).total_seconds() / 86400
            signals = {
                "similarity": _clamp(similarities.get(memory.id, 0.0)),
                "importance": _clamp(memory.importance / 10),
                "recency": _clamp(math.exp(-max(age_days, 0.0) * math.log(2) / RECENCY_HALF_LIFE_DAYS)),
                "access_frequency": _clamp(memory.access_count / max_access) if max_access else 0.0,
            }
            components[memory.id] = signals
            scores[memory.id] = sum(WEIGHTS[name] * value for name, value in signals.items())

        # Deterministic: ties broken by id (ULIDs are time-sortable).
        ranked = sorted(retrieval.retrieved_memories, key=lambda m: (-scores[m.id], m.id))[:top_k]

        return RankingResult(
            ranked_memories=ranked,
            ranking_scores=scores,
            selected_memory_ids=[m.id for m in ranked],
            ranking_metadata={
                "weights": WEIGHTS,
                "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
                "components": components,
                "requested_top_k": top_k,
            },
        )
