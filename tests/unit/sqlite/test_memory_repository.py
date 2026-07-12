"""MemoryRepository.touch: reinforcement recency + confidence-upgrade-only."""

from tests.conftest import make_memory

from app.memory.repositories.memory_repository import MemoryRepository
from app.models.enums import Confidence


def test_touch_bumps_recency_and_upgrades_confidence(db_conn):
    repo = MemoryRepository(db_conn)
    memory = make_memory(confidence=Confidence.MEDIUM)
    repo.save(memory)
    before = repo.get(memory.id).updated_at

    repo.touch(memory.id, confidence=Confidence.HIGH)

    after = repo.get(memory.id)
    assert after.confidence is Confidence.HIGH
    assert after.updated_at >= before


def test_touch_never_downgrades_confidence(db_conn):
    repo = MemoryRepository(db_conn)
    memory = make_memory(confidence=Confidence.HIGH)
    repo.save(memory)

    repo.touch(memory.id, confidence=Confidence.LOW)

    assert repo.get(memory.id).confidence is Confidence.HIGH


def test_touch_without_confidence_only_bumps_recency(db_conn):
    repo = MemoryRepository(db_conn)
    memory = make_memory(confidence=Confidence.MEDIUM)
    repo.save(memory)

    repo.touch(memory.id)

    assert repo.get(memory.id).confidence is Confidence.MEDIUM
