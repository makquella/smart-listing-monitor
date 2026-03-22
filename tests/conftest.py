from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models import (  # noqa: F401
    ai_summary,
    event,
    item,
    monitor_match,
    monitor_profile,
    notification,
    notification_delivery,
    run,
    source,
    telegram_chat,
    telegram_user,
)


@pytest.fixture()
def session_factory(tmp_path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    yield factory
    Base.metadata.drop_all(bind=engine)
