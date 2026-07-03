import pytest

from app.engine.classifier.memory_classifier import ClassificationResult
from app.engine.router.storage_router import RuleStorageRouter
from app.engine.scorer.importance_scorer import ScoringResult
from app.models.enums import ClassifierAction, MemoryCategory, MemoryView

router = RuleStorageRouter()


def route(message, category=MemoryCategory.LEARNING, project_id=None, modifiers=()):
    classification = ClassificationResult(action=ClassifierAction.STORE, category=category)
    scoring = ScoringResult(importance=5, base_score=5, applied_modifiers=list(modifiers))
    return router.route(classification, scoring, message, project_id)


CASES = [
    # message, category, project_id, modifiers, expected view
    # PROFILE — personal facts, even when a project is active
    ("I prefer diagrams over text.", MemoryCategory.PREFERENCE, None, (), MemoryView.PROFILE),
    ("I prefer diagrams over text.", MemoryCategory.PREFERENCE, "proj_x", (), MemoryView.PROFILE),
    ("My favorite editor is Neovim.", MemoryCategory.PREFERENCE, None, (), MemoryView.PROFILE),
    ("I am a backend developer.", MemoryCategory.LEARNING, None, (), MemoryView.PROFILE),
    ("My birthday is in June.", MemoryCategory.LEARNING, None, (), MemoryView.PROFILE),
    ("My laptop has 16GB of RAM.", MemoryCategory.LEARNING, None, (), MemoryView.PROFILE),
    # PROJECT — anchored to a project
    ("We'll use FastAPI.", MemoryCategory.DECISION, "proj_x", (), MemoryView.PROJECT),
    ("Found a bug in ranking.", MemoryCategory.BUG, "proj_x", (), MemoryView.PROJECT),
    ("Which store should we pick?", MemoryCategory.QUESTION, "proj_x", (), MemoryView.PROJECT),
    # EPISODIC — session-bound events without a project
    ("Sprint review recap: shipped Phase 1.", MemoryCategory.MEETING, None, (), MemoryView.EPISODIC),
    ("V1 launch happened.", MemoryCategory.MILESTONE, None, (), MemoryView.EPISODIC),
    # but the same event WITH a project routes to the project
    ("Sprint review recap.", MemoryCategory.MEETING, "proj_x", (), MemoryView.PROJECT),
    # WORKING — explicitly transient, unanchored
    ("Use the staging db today.", MemoryCategory.TASK, None, ("temporary(-1)",), MemoryView.WORKING),
    # SEMANTIC — durable unanchored knowledge (default)
    ("ULIDs are time-sortable identifiers.", MemoryCategory.RESEARCH, None, (), MemoryView.SEMANTIC),
    ("Transformers use attention.", MemoryCategory.LEARNING, None, (), MemoryView.SEMANTIC),
    ("Vector search scales with HNSW.", MemoryCategory.IDEA, None, (), MemoryView.SEMANTIC),
    # default for unknown/uncategorized without signals
    ("Some fact worth keeping.", None, None, (), MemoryView.SEMANTIC),
]


@pytest.mark.parametrize("message, category, project_id, modifiers, view", CASES)
def test_routing_table(message, category, project_id, modifiers, view):
    assert route(message, category, project_id, modifiers).view is view


def test_every_view_is_reachable():
    reached = {route(m, c, p, mods).view for m, c, p, mods, _ in CASES}
    assert reached == set(MemoryView)


def test_result_is_typed_and_explains_itself():
    result = route("We'll use FastAPI.", MemoryCategory.DECISION, "proj_x")
    assert result.view is MemoryView.PROJECT
    assert result.matched_rule == "has_project"
    assert "proj_x" in result.reasoning


def test_transient_with_project_still_routes_to_project():
    # temporary modifier does not pull project-anchored memories into WORKING
    result = route("Deploy today.", MemoryCategory.TASK, "proj_x", ("temporary(-1)",))
    assert result.view is MemoryView.PROJECT
