from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import StatementError

from app.core.time import utcnow
from app.models.source import Source


def test_utcnow_returns_aware_utc_datetime() -> None:
    value = utcnow()

    assert value.tzinfo is not None
    assert value.utcoffset() == UTC.utcoffset(value)


def test_datetime_roundtrip_preserves_aware_utc(session_factory) -> None:
    with session_factory() as session:
        now = utcnow()
        source = Source(
            name="Time Source",
            slug="time-source",
            parser_key="fake",
            base_url="https://example.com/",
            start_url="https://example.com/catalogue",
            schedule_enabled=True,
            schedule_interval_minutes=60,
            is_active=True,
            health_status="healthy",
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        source_id = source.id

    with session_factory() as session:
        persisted = session.get(Source, source_id)

    assert persisted is not None
    assert persisted.created_at.tzinfo is not None
    assert persisted.created_at.utcoffset() == UTC.utcoffset(persisted.created_at)
    assert persisted.updated_at.tzinfo is not None
    assert persisted.updated_at.utcoffset() == UTC.utcoffset(persisted.updated_at)


def test_naive_datetimes_are_rejected_on_persist(session_factory) -> None:
    with session_factory() as session:
        naive_now = datetime.now()
        source = Source(
            name="Naive Source",
            slug="naive-source",
            parser_key="fake",
            base_url="https://example.com/",
            start_url="https://example.com/catalogue",
            schedule_enabled=True,
            schedule_interval_minutes=60,
            is_active=True,
            health_status="healthy",
            consecutive_failures=0,
            created_at=naive_now,
            updated_at=naive_now,
        )
        session.add(source)
        with pytest.raises((ValueError, StatementError)):
            session.commit()
