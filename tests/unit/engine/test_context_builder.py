from app.engine.context.context_builder import ContextBuilder
from app.engine.retrieval.ranking_engine import RankingResult
from app.models.enums import Confidence, MemoryCategory, MemoryView
from app.services.tokenizer_service import estimate_tokens
from tests.conftest import make_memory

builder = ContextBuilder()


def mem(**overrides):
    overrides.setdefault("summary", None)
    return make_memory(**overrides)


def ranked(*memories) -> RankingResult:
    """Memories are already in ranking order — build the result the ranker would emit."""
    return RankingResult(
        ranked_memories=list(memories),
        ranking_scores={m.id: 1.0 - i / 10 for i, m in enumerate(memories)},
        selected_memory_ids=[m.id for m in memories],
    )


def test_empty_ranking_result():
    pack = builder.build(ranked(), session_id="s1")
    assert pack.session_id == "s1"
    assert pack.sections.project_state is None
    assert pack.sections.profile == []
    assert pack.sections.relevant_memories == []
    assert pack.sections.open_questions == []
    assert pack.token_estimate == 0


def test_project_state_included_and_counted():
    pack = builder.build(ranked(), session_id="s1", project_state="Backend = FastAPI")
    assert pack.sections.project_state == "Backend = FastAPI"
    assert pack.token_estimate == estimate_tokens("Backend = FastAPI")


def test_profile_section_from_arg_and_ranked_profile_views():
    given = mem(
        content="Prefers diagrams", view=MemoryView.PROFILE, project_id=None,
        category=MemoryCategory.PREFERENCE,
    )
    ranked_profile = mem(
        content="Works in Python", view=MemoryView.PROFILE, project_id=None,
        category=MemoryCategory.LEARNING,
    )
    pack = builder.build(ranked(ranked_profile), session_id="s1", profile_memories=[given])
    assert pack.sections.profile == ["Prefers diagrams", "Works in Python"]


def test_profile_memories_not_duplicated_when_also_ranked():
    memory = mem(
        content="Prefers diagrams", view=MemoryView.PROFILE, project_id=None,
        category=MemoryCategory.PREFERENCE,
    )
    pack = builder.build(ranked(memory), session_id="s1", profile_memories=[memory])
    assert pack.sections.profile == ["Prefers diagrams"]


def test_relevant_memories_grouped_by_category_preserving_rank():
    d1 = mem(content="decision 1", category=MemoryCategory.DECISION)
    b1 = mem(content="bug 1", category=MemoryCategory.BUG)
    d2 = mem(content="decision 2", category=MemoryCategory.DECISION)
    pack = builder.build(ranked(d1, b1, d2), session_id="s1")

    entries = [(m.category, m.summary) for m in pack.sections.relevant_memories]
    # decision group first (best-ranked member), rank order inside the group
    assert entries == [
        (MemoryCategory.DECISION, "decision 1"),
        (MemoryCategory.DECISION, "decision 2"),
        (MemoryCategory.BUG, "bug 1"),
    ]
    assert all(m.confidence is Confidence.HIGH for m in pack.sections.relevant_memories)


def test_open_questions_extracted():
    question = mem(content="Which store should we pick?", category=MemoryCategory.QUESTION)
    decision = mem(content="We use FastAPI.", category=MemoryCategory.DECISION)
    pack = builder.build(ranked(question, decision), session_id="s1")

    assert pack.sections.open_questions == ["Which store should we pick?"]
    assert [m.summary for m in pack.sections.relevant_memories] == ["We use FastAPI."]


def test_summary_preferred_content_fallback():
    with_summary = mem(content="long content", summary="short summary")
    without = mem(content="only content")
    pack = builder.build(ranked(with_summary, without), session_id="s1")
    assert [m.summary for m in pack.sections.relevant_memories] == ["short summary", "only content"]


def test_budget_trims_lowest_ranked_relevant_first(monkeypatch):
    from app.core.config import get_settings

    memories = [mem(content=f"decision {'x' * 100} {i}") for i in range(5)]
    each = estimate_tokens(memories[0].content)
    monkeypatch.setattr(
        get_settings(), "context_token_budget", each * 3, raising=True
    )
    pack = builder.build(ranked(*memories), session_id="s1")

    kept = [m.summary for m in pack.sections.relevant_memories]
    assert kept == [m.content for m in memories[:3]]  # lowest-ranked two dropped
    assert pack.token_estimate <= each * 3


def test_mandatory_sections_survive_impossible_budget(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "context_token_budget", 1, raising=True)
    profile = mem(
        content="Prefers diagrams", view=MemoryView.PROFILE, project_id=None,
        category=MemoryCategory.PREFERENCE,
    )
    pack = builder.build(
        ranked(mem(content="a decision")),
        session_id="s1",
        project_state="State",
        profile_memories=[profile],
    )
    assert pack.sections.project_state == "State"  # never trimmed
    assert pack.sections.profile == ["Prefers diagrams"]  # never trimmed
    assert pack.sections.relevant_memories == []  # all trimmed


def test_deterministic_output():
    a = mem(content="a", category=MemoryCategory.DECISION)
    b = mem(content="b", category=MemoryCategory.BUG)
    first = builder.build(ranked(a, b), session_id="s1").sections
    second = builder.build(ranked(a, b), session_id="s1").sections
    assert first == second
