"""Time helpers. All timestamps in the system are timezone-aware UTC."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
