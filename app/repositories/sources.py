from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import utcnow
from app.models.source import Source
from app.repositories.query_filters import text_search_clause


class SourceRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_sources(self) -> list[Source]:
        statement = select(Source).order_by(Source.name.asc())
        return list(self.session.scalars(statement))

    def list_for_admin(
        self,
        *,
        health_status: str | None = None,
        is_active: bool | None = None,
        schedule_enabled: bool | None = None,
        attention_only: bool = False,
        search_query: str | None = None,
    ) -> list[Source]:
        statement = select(Source)
        if health_status:
            statement = statement.where(Source.health_status == health_status)
        if is_active is not None:
            statement = statement.where(Source.is_active.is_(is_active))
        if schedule_enabled is not None:
            statement = statement.where(Source.schedule_enabled.is_(schedule_enabled))
        if attention_only:
            statement = statement.where(
                (Source.health_status == "failing") | (Source.is_active.is_(False))
            )
        if search_query:
            statement = statement.where(
                text_search_clause(
                    search_query,
                    [
                        Source.name,
                        Source.slug,
                        Source.parser_key,
                        Source.base_url,
                        Source.start_url,
                        Source.health_status,
                    ],
                )
            )
        statement = statement.order_by(Source.name.asc())
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
        sources = self.ensure_seed_sources(settings)
        for source in sources:
            if source.slug == settings.books_source_slug:
                return source
        raise RuntimeError("Primary seed source is not available")

    def ensure_seed_sources(self, settings: Settings) -> list[Source]:
        seeded: list[Source] = []
        for config in self._seed_source_configs(settings):
            existing = self.get_by_slug(config["slug"])
            if existing is not None:
                seeded.append(existing)
                continue

            now = utcnow()
            source = Source(
                name=config["name"],
                slug=config["slug"],
                parser_key=config["parser_key"],
                base_url=config["base_url"],
                start_url=config["start_url"],
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
            seeded.append(source)

        return seeded

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

    @staticmethod
    def _seed_source_configs(settings: Settings) -> list[dict[str, str]]:
        configs = [
            {
                "name": settings.books_source_name,
                "slug": settings.books_source_slug,
                "parser_key": "books_toscrape",
                "base_url": settings.books_source_base_url,
                "start_url": settings.books_source_start_url,
            }
        ]
        if settings.seed_additional_demo_sources:
            configs.append(
                {
                    "name": settings.webscraper_source_name,
                    "slug": settings.webscraper_source_slug,
                    "parser_key": "webscraper_static_ecommerce",
                    "base_url": settings.webscraper_source_base_url,
                    "start_url": settings.webscraper_source_start_url,
                }
            )
        return configs
