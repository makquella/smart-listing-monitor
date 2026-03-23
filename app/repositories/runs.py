from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.run import MonitoringRun
from app.models.source import Source
from app.repositories.query_filters import text_search_clause


class RunRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_run(
        self,
        *,
        source_id: int,
        trigger_type: str,
        started_at: datetime,
        status: str = "running",
    ) -> MonitoringRun:
        run = MonitoringRun(
            source_id=source_id,
            trigger_type=trigger_type,
            status=status,
            started_at=started_at,
            created_at=started_at,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def save(self, run: MonitoringRun) -> MonitoringRun:
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get(self, run_id: int) -> MonitoringRun | None:
        return self.session.get(MonitoringRun, run_id)

    def get_in_progress_by_source(self, source_id: int) -> MonitoringRun | None:
        statement = (
            select(MonitoringRun)
            .where(
                MonitoringRun.source_id == source_id,
                MonitoringRun.status.in_(("queued", "running")),
            )
            .order_by(desc(MonitoringRun.created_at))
            .limit(1)
        )
        return self.session.scalar(statement)

    def list_recent(self, limit: int = 20) -> Sequence[MonitoringRun]:
        statement = select(MonitoringRun).order_by(desc(MonitoringRun.started_at)).limit(limit)
        return list(self.session.scalars(statement))

    def list_for_admin(
        self,
        *,
        limit: int = 30,
        status: str | None = None,
        trigger_type: str | None = None,
        source_id: int | None = None,
        search_query: str | None = None,
    ) -> Sequence[MonitoringRun]:
        statement = select(MonitoringRun).outerjoin(Source, Source.id == MonitoringRun.source_id)
        if status:
            statement = statement.where(MonitoringRun.status == status)
        if trigger_type:
            statement = statement.where(MonitoringRun.trigger_type == trigger_type)
        if source_id is not None:
            statement = statement.where(MonitoringRun.source_id == source_id)
        if search_query:
            statement = statement.where(
                text_search_clause(
                    search_query,
                    [
                        MonitoringRun.id,
                        MonitoringRun.status,
                        MonitoringRun.trigger_type,
                        MonitoringRun.error_message,
                        Source.name,
                    ],
                )
            )
        statement = statement.order_by(desc(MonitoringRun.started_at)).limit(limit)
        return list(self.session.scalars(statement).unique())

    def list_recent_by_source(self, source_id: int, limit: int = 10) -> Sequence[MonitoringRun]:
        statement = (
            select(MonitoringRun)
            .where(MonitoringRun.source_id == source_id)
            .order_by(desc(MonitoringRun.started_at))
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def recent_healthy_item_counts(self, source_id: int, limit: int) -> list[int]:
        statement = (
            select(MonitoringRun.items_parsed)
            .where(
                MonitoringRun.source_id == source_id,
                MonitoringRun.status.in_(("succeeded", "degraded")),
                MonitoringRun.health_evaluation == "healthy",
            )
            .order_by(desc(MonitoringRun.started_at))
            .limit(limit)
        )
        return [count for count in self.session.scalars(statement) if count]
