from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.monitor_profile import MonitorProfile


class MonitorProfileRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, monitor_profile_id: int) -> MonitorProfile | None:
        return self.session.get(MonitorProfile, monitor_profile_id)

    def save(self, profile: MonitorProfile) -> MonitorProfile:
        self.session.add(profile)
        self.session.flush()
        return profile

    def delete(self, profile: MonitorProfile) -> None:
        self.session.delete(profile)
        self.session.flush()

    def list_recent(self, limit: int = 50) -> Sequence[MonitorProfile]:
        statement = select(MonitorProfile).order_by(desc(MonitorProfile.updated_at)).limit(limit)
        return list(self.session.scalars(statement))

    def list_by_chat(self, chat_id: int) -> Sequence[MonitorProfile]:
        statement = (
            select(MonitorProfile)
            .where(MonitorProfile.telegram_chat_id == chat_id)
            .order_by(MonitorProfile.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def list_active_by_source(self, source_id: int) -> Sequence[MonitorProfile]:
        statement = (
            select(MonitorProfile)
            .where(MonitorProfile.source_id == source_id, MonitorProfile.is_active.is_(True))
            .order_by(MonitorProfile.created_at.asc())
        )
        return list(self.session.scalars(statement))
