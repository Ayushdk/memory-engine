import pytest

from app.engine.classifier.memory_classifier import ClassificationResult
from app.engine.scorer.importance_scorer import RuleImportanceScorer, create_scorer
from app.engine.scorer.scoring_policy import BASE_SCORES
from app.models.enums import ClassifierAction, MemoryCategory

scorer = RuleImportanceScorer()


def classified(category: MemoryCategory | None) -> ClassificationResult:
    return ClassificationResult(action=ClassifierAction.STORE, category=category)


# A message with no modifier signal words, so base scores show through untouched.
NEUTRAL = "the backend uses a unified store"


@pytest.mark.parametrize("category, expected_base", list(BASE_SCORES.items()))
def test_every_category_base_score(category, expected_base):
    result = scorer.score(classified(category), NEUTRAL)
    assert result.base_score == expected_base
    assert result.importance == expected_base
    assert result.applied_modifiers == []


MODIFIER_CASES = [
    # message, project_id, expected modifier names, expected delta
    (NEUTRAL, "proj_x", ["has_project(+1)"], +1),
    ("we always use black for formatting", None, ["permanence(+1)"], +1),
    ("this is the default retry policy", None, ["permanence(+1)"], +1),
    ("the migration is required before launch", None, ["dependency(+1)"], +1),
    ("auth depends on the session table", None, ["dependency(+1)"], +1),
    ("this is critical for the demo", None, ["emphasis(+1)"], +1),
    ("we must keep ids time-sortable", None, ["emphasis(+1)"], +1),
    ("deploy the fix today", None, ["temporary(-1)"], -1),
    ("standup moved to 10am this week", None, ["temporary(-1)"], -1),
]


@pytest.mark.parametrize("message, project_id, names, delta", MODIFIER_CASES)
def test_each_modifier(message, project_id, names, delta):
    result = scorer.score(classified(MemoryCategory.LEARNING), message, project_id)
    assert result.applied_modifiers == names
    assert result.importance == BASE_SCORES[MemoryCategory.LEARNING] + delta


def test_multiple_modifiers_stack():
    result = scorer.score(
        classified(MemoryCategory.BUG),
        "fixing this is critical and required before the demo",
        project_id="proj_x",
    )
    assert result.applied_modifiers == [
        "has_project(+1)",
        "dependency(+1)",
        "emphasis(+1)",
    ]
    assert result.importance == 6 + 3


def test_clamped_to_upper_bound():
    result = scorer.score(
        classified(MemoryCategory.DECISION),
        "we must always use the required standard",
        project_id="proj_x",
    )
    assert result.base_score == 9
    assert result.importance == 10  # 9 + 4 clamped


def test_clamped_to_lower_bound():
    # No category (e.g. a delete command) → base 0; a negative modifier can't go below 0.
    no_category = ClassificationResult(action=ClassifierAction.DELETE, category=None)
    result = scorer.score(no_category, "forget the plan for today")
    assert result.base_score == 0
    assert result.importance == 0


def test_informational_question_penalty():
    result = scorer.score(classified(MemoryCategory.QUESTION), "What is a ULID?")
    assert result.applied_modifiers == ["informational_question(-1)"]
    assert result.importance == 2


def test_decision_seeking_question_keeps_base():
    result = scorer.score(classified(MemoryCategory.QUESTION), "Which vector store should we pick?")
    assert result.applied_modifiers == []
    assert result.importance == 3


def test_long_term_beats_short_term():
    long_term = scorer.score(classified(MemoryCategory.PREFERENCE), "I always want type hints")
    short_term = scorer.score(classified(MemoryCategory.PREFERENCE), "use the staging db today")
    assert long_term.importance > short_term.importance


def test_word_boundary_matching():
    # 'must' inside 'mustard' is not emphasis
    result = scorer.score(classified(MemoryCategory.PREFERENCE), "i like mustard on sandwiches")
    assert result.applied_modifiers == []


def test_factory():
    assert isinstance(create_scorer("rules"), RuleImportanceScorer)
    with pytest.raises(NotImplementedError):
        create_scorer("gemini")
