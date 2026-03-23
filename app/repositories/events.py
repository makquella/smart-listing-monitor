from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.event import DetectedEvent
from app.models.source import Source
from app.repositories.query_filters import text_search_clause


class EventRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, event: DetectedEvent) -> DetectedEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def save_all(self, events: Sequence[DetectedEvent]) -> list[DetectedEvent]:
        if not events:
            return []
        self.session.add_all(events)
        return list(events)

    def list_recent(self, limit: int = 25) -> Sequence[DetectedEvent]:
        statement = select(DetectedEvent).order_by(desc(DetectedEvent.created_at)).limit(limit)
        return list(self.session.scalars(statement))

    def list_for_admin(
        self,
        *,
        limit: int | None = 40,
        run_id: int | None = None,
        source_id: int | None = None,
        item_id: int | None = None,
        severity: str | None = None,
        event_type: str | None = None,
        suppressed: bool | None = None,
        search_query: str | None = None,
    ) -> Sequence[DetectedEvent]:
        statement = select(DetectedEvent).outerjoin(Source, Source.id == DetectedEvent.source_id)
        if run_id is not None:
            statement = statement.where(DetectedEvent.run_id == run_id)
        if source_id is not None:
            statement = statement.where(DetectedEvent.source_id == source_id)
        if item_id is not None:
            statement = statement.where(DetectedEvent.item_id == item_id)
        if severity:
            statement = statement.where(DetectedEvent.severity == severity)
        if event_type:
            statement = statement.where(DetectedEvent.event_type == event_type)
        if suppressed is not None:
            statement = statement.where(DetectedEvent.is_suppressed.is_(suppressed))
        if search_query:
            statement = statement.where(
                text_search_clause(
                    search_query,
                    [
                        DetectedEvent.event_type,
                        DetectedEvent.severity,
                        DetectedEvent.summary_text,
                        Source.name,
                    ],
                )
            )
        statement = statement.order_by(desc(DetectedEvent.created_at))
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement).unique())

    def list_by_run(self, run_id: int) -> Sequence[DetectedEvent]:
        statement = (
            select(DetectedEvent)
            .where(DetectedEvent.run_id == run_id)
            .order_by(desc(DetectedEvent.created_at))
        )
        return list(self.session.scalars(statement))

    def list_recent_by_item(self, item_id: int, limit: int = 20) -> Sequence[DetectedEvent]:
        statement = (
            select(DetectedEvent)
            .where(DetectedEvent.item_id == item_id)
            .order_by(desc(DetectedEvent.created_at))
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def latest_unsuppressed_for_dedupe_key(
        self, dedupe_key: str, since: datetime
    ) -> DetectedEvent | None:
        statement = (
            select(DetectedEvent)
            .where(
                DetectedEvent.dedupe_key == dedupe_key,
                DetectedEvent.is_suppressed.is_(False),
                DetectedEvent.created_at >= since,
            )
            .order_by(desc(DetectedEvent.created_at))
            .limit(1)
        )
        return self.session.scalar(statement)

    def latest_unsuppressed_for_dedupe_keys(
        self, dedupe_keys: Sequence[str], since: datetime
    ) -> dict[str, DetectedEvent]:
        if not dedupe_keys:
            return {}

        statement = (
            select(DetectedEvent)
            .where(
                DetectedEvent.dedupe_key.in_(dedupe_keys),
                DetectedEvent.is_suppressed.is_(False),
                DetectedEvent.created_at >= since,
            )
            .order_by(DetectedEvent.dedupe_key.asc(), desc(DetectedEvent.created_at))
        )

        latest_by_key: dict[str, DetectedEvent] = {}
        for event in self.session.scalars(statement):
            latest_by_key.setdefault(event.dedupe_key, event)
        return latest_by_key
