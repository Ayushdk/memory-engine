import pytest

from app.engine.classifier.memory_classifier import RuleClassifier, create_classifier
from app.models.enums import ClassifierAction, MemoryCategory

classifier = RuleClassifier()

CASES = [
    # message, expected action, expected category
    # STORE — decisions
    ("I decided to use SQLite as the source of truth.", ClassifierAction.STORE, MemoryCategory.DECISION),
    ("We'll use FastAPI for the backend.", ClassifierAction.STORE, MemoryCategory.DECISION),
    ("we decided on ChromaDB", ClassifierAction.STORE, MemoryCategory.DECISION),
    ("Let's go with MiniLM embeddings.", ClassifierAction.STORE, MemoryCategory.DECISION),
    # STORE — preferences
    ("I prefer diagrams over long text.", ClassifierAction.STORE, MemoryCategory.PREFERENCE),
    ("My favorite editor is Neovim.", ClassifierAction.STORE, MemoryCategory.PREFERENCE),
    ("I like short answers.", ClassifierAction.STORE, MemoryCategory.PREFERENCE),
    # STORE — goals / bugs / tasks
    ("Our goal is to ship V1 by March.", ClassifierAction.STORE, MemoryCategory.GOAL),
    ("There's a bug in the retrieval ranking.", ClassifierAction.STORE, MemoryCategory.BUG),
    ("The ingest endpoint crashes on empty content.", ClassifierAction.STORE, MemoryCategory.BUG),
    ("We need to add tests for the router.", ClassifierAction.STORE, MemoryCategory.TASK),
    # STORE — questions
    ("Which vector store should we pick?", ClassifierAction.STORE, MemoryCategory.QUESTION),
    # UPDATE — revisions
    ("We switched to FastAPI.", ClassifierAction.UPDATE, MemoryCategory.DECISION),
    ("We changed the schema to include tags.", ClassifierAction.UPDATE, MemoryCategory.DECISION),
    ("Instead of Flask, use FastAPI.", ClassifierAction.UPDATE, MemoryCategory.DECISION),
    ("We're no longer using Redis.", ClassifierAction.UPDATE, MemoryCategory.DECISION),
    # DELETE / MERGE — commands
    ("Delete the memory about Flask.", ClassifierAction.DELETE, None),
    ("Forget what I said about deadlines.", ClassifierAction.DELETE, None),
    ("Merge the two FastAPI memories.", ClassifierAction.MERGE, None),
    # IGNORE — smalltalk
    ("Thanks", ClassifierAction.IGNORE, None),
    ("Okay", ClassifierAction.IGNORE, None),
    ("cool!", ClassifierAction.IGNORE, None),
    ("Nice.", ClassifierAction.IGNORE, None),
    ("Hello", ClassifierAction.IGNORE, None),
    ("Good morning", ClassifierAction.IGNORE, None),
    # IGNORE — unmatched ordinary conversation
    ("The weather API returns JSON.", ClassifierAction.IGNORE, None),
    ("That paragraph explains the tradeoff.", ClassifierAction.IGNORE, None),
    # Negative cases: greetings embedded in substantive messages are NOT smalltalk
    ("Okay, we'll use Postgres for analytics.", ClassifierAction.STORE, MemoryCategory.DECISION),
    ("Thanks! I decided to keep the ULID ids.", ClassifierAction.STORE, MemoryCategory.DECISION),
    # Negative case: 'delete' mid-sentence is not a delete command
    ("We decided to delete the legacy module.", ClassifierAction.STORE, MemoryCategory.DECISION),
]


@pytest.mark.parametrize("message, action, category", CASES)
def test_classification_table(message, action, category):
    result = classifier.classify(message)
    assert result.action is action
    assert result.category is category


def test_unmatched_result_shape():
    result = classifier.classify("The weather API returns JSON.")
    assert result.action is ClassifierAction.IGNORE
    assert result.category is None
    assert result.matched_rule is None
    assert result.reason == "no_matching_rule"


def test_matched_result_carries_rule_name():
    result = classifier.classify("We switched to FastAPI.")
    assert result.matched_rule == "revision"
    assert result.reason


def test_case_insensitive():
    assert classifier.classify("I DECIDED TO USE SQLITE").action is ClassifierAction.STORE


def test_factory_returns_rules_strategy():
    assert isinstance(create_classifier("rules"), RuleClassifier)


def test_factory_rejects_unimplemented_strategy():
    with pytest.raises(NotImplementedError):
        create_classifier("ollama")
