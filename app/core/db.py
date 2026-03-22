from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(
    settings.resolved_database_url,
    connect_args={"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
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

    Base.metadata.create_all(bind=engine)
