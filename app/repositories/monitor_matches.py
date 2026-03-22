from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.monitor_match import MonitorMatch


class MonitorMatchRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, match: MonitorMatch) -> MonitorMatch:
        self.session.add(match)
        self.session.flush()
        return match

    def list_recent(self, limit: int = 50) -> Sequence[MonitorMatch]:
        statement = select(MonitorMatch).order_by(desc(MonitorMatch.created_at)).limit(limit)
        return list(self.session.scalars(statement))

    def list_by_monitor(self, monitor_profile_id: int, limit: int = 50) -> Sequence[MonitorMatch]:
        statement = (
            select(MonitorMatch)
            .where(MonitorMatch.monitor_profile_id == monitor_profile_id)
            .order_by(desc(MonitorMatch.created_at))
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_by_run(self, monitoring_run_id: int) -> Sequence[MonitorMatch]:
        statement = (
            select(MonitorMatch)
            .where(MonitorMatch.monitoring_run_id == monitoring_run_id)
            .order_by(desc(MonitorMatch.created_at))
        )
        return list(self.session.scalars(statement))
