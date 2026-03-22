from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import utcnow
from app.models.source import Source


class SourceRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_sources(self) -> list[Source]:
        statement = select(Source).order_by(Source.name.asc())
        return list(self.session.scalars(statement))

    def list_scheduled_sources(self) -> list[Source]:
        statement = select(Source).where(
            Source.is_active.is_(True),
            Source.schedule_enabled.is_(True),
        )
        return list(self.session.scalars(statement))

    def get(self, source_id: int) -> Source | None:
        return self.session.get(Source, source_id)

    def get_by_slug(self, slug: str) -> Source | None:
        statement = select(Source).where(Source.slug == slug)
        return self.session.scalar(statement)

    def ensure_seed_source(self, settings: Settings) -> Source:
        existing = self.get_by_slug(settings.books_source_slug)
        if existing:
            return existing

        now = utcnow()
        source = Source(
            name=settings.books_source_name,
            slug=settings.books_source_slug,
            parser_key="books_toscrape",
            base_url=settings.books_source_base_url,
            start_url=settings.books_source_start_url,
            schedule_enabled=True,
            schedule_interval_minutes=settings.schedule_default_interval_minutes,
            is_active=True,
            health_status="healthy",
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source

    def update_schedule(
        self,
        source: Source,
        *,
        schedule_enabled: bool,
        is_active: bool,
        schedule_interval_minutes: int,
    ) -> Source:
        source.schedule_enabled = schedule_enabled
        source.is_active = is_active
        source.schedule_interval_minutes = schedule_interval_minutes
        source.updated_at = utcnow()
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source
