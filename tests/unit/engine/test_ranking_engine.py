from datetime import timedelta

import pytest

from app.engine.retrieval.ranking_engine import RankingEngine, RankingResult
from app.engine.retrieval.retrieval_engine import RetrievalResult
from app.utils.time import utc_now
from tests.conftest import make_memory

engine = RankingEngine()


def retrieval_of(memories, similarities):
    return RetrievalResult(
        query_embedding=[0.0],
        candidate_memory_ids=[m.id for m in memories],
        retrieved_memories=list(memories),
        retrieval_metadata={"similarities": similarities},
    )


def fresh(**overrides):
    now = utc_now()
    defaults = dict(created_at=now, updated_at=now, importance=5, access_count=0)
    return make_memory(**{**defaults, **overrides})


def test_similarity_dominates_when_all_else_equal():
    close, far = fresh(content="close"), fresh(content="far")
    result = engine.rank(retrieval_of([far, close], {close.id: 0.9, far.id: 0.1}))
    assert result.selected_memory_ids == [close.id, far.id]


def test_importance_dominates_when_similarity_equal():
    major, minor = fresh(importance=10), fresh(importance=1)
    result = engine.rank(retrieval_of([minor, major], {major.id: 0.5, minor.id: 0.5}))
    assert result.selected_memory_ids == [major.id, minor.id]


def test_recency_influences_ranking():
    old = fresh(updated_at=utc_now() - timedelta(days=120))
    new = fresh()
    result = engine.rank(retrieval_of([old, new], {old.id: 0.5, new.id: 0.5}))
    assert result.selected_memory_ids == [new.id, old.id]
    components = result.ranking_metadata["components"]
    assert components[new.id]["recency"] == pytest.approx(1.0)
    assert components[old.id]["recency"] == pytest.approx(0.0625)  # 4 half-lives


def test_access_frequency_influences_ranking():
    popular, untouched = fresh(access_count=8), fresh(access_count=0)
    result = engine.rank(retrieval_of([untouched, popular], {popular.id: 0.5, untouched.id: 0.5}))
    assert result.selected_memory_ids == [popular.id, untouched.id]
    assert result.ranking_metadata["components"][popular.id]["access_frequency"] == 1.0


def test_normalization_and_clamping():
    memory = fresh(importance=10, access_count=3)
    result = engine.rank(retrieval_of([memory], {memory.id: 1.7}))  # out-of-range similarity
    signals = result.ranking_metadata["components"][memory.id]
    assert signals["similarity"] == 1.0  # clamped
    assert all(0.0 <= v <= 1.0 for v in signals.values())
    # perfect signals → score = sum of weights = 1.0
    assert result.ranking_scores[memory.id] == pytest.approx(1.0)


def test_weighted_formula_is_exact():
    memory = fresh(importance=6, access_count=0)
    result = engine.rank(retrieval_of([memory], {memory.id: 0.8}))
    expected = 0.45 * 0.8 + 0.25 * 0.6 + 0.20 * 1.0 + 0.10 * 0.0
    assert result.ranking_scores[memory.id] == pytest.approx(expected)


def test_top_k():
    memories = [fresh(content=f"m{i}") for i in range(5)]
    sims = {m.id: 0.5 for m in memories}
    assert len(engine.rank(retrieval_of(memories, sims), top_k=2).ranked_memories) == 2
    # default comes from Settings.retrieval_top_k (15) — all 5 fit
    assert len(engine.rank(retrieval_of(memories, sims)).ranked_memories) == 5
    # ranking_scores still covers ALL candidates even when top_k trims the selection
    assert len(engine.rank(retrieval_of(memories, sims), top_k=2).ranking_scores) == 5


def test_deterministic_ordering_on_ties():
    a, b, c = (fresh(content=x) for x in "abc")
    sims = {m.id: 0.5 for m in (a, b, c)}
    first = engine.rank(retrieval_of([b, c, a], sims)).selected_memory_ids
    second = engine.rank(retrieval_of([c, a, b], sims)).selected_memory_ids
    assert first == second == sorted([a.id, b.id, c.id])  # ULID tie-break


def test_empty_candidates():
    result = engine.rank(retrieval_of([], {}))
    assert isinstance(result, RankingResult)
    assert result.ranked_memories == []
    assert result.selected_memory_ids == []
    assert result.ranking_scores == {}


def test_ranking_has_no_side_effects():
    memory = fresh(access_count=2)
    engine.rank(retrieval_of([memory], {memory.id: 0.5}))
    assert memory.access_count == 2  # never touched
