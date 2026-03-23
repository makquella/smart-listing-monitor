from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.monitor_profile import MonitorProfile
from app.models.source import Source
from app.models.telegram_chat import TelegramChat
from app.models.telegram_user import TelegramUser
from app.repositories.query_filters import text_search_clause


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

    def list_for_admin(
        self,
        *,
        limit: int = 60,
        source_id: int | None = None,
        is_active: bool | None = None,
        priority_mode: str | None = None,
        instant_alerts_enabled: bool | None = None,
        digest_enabled: bool | None = None,
        search_query: str | None = None,
    ) -> Sequence[MonitorProfile]:
        statement = (
            select(MonitorProfile)
            .outerjoin(Source, Source.id == MonitorProfile.source_id)
            .outerjoin(TelegramChat, TelegramChat.id == MonitorProfile.telegram_chat_id)
            .outerjoin(TelegramUser, TelegramUser.id == MonitorProfile.telegram_user_id)
        )
        if source_id is not None:
            statement = statement.where(MonitorProfile.source_id == source_id)
        if is_active is not None:
            statement = statement.where(MonitorProfile.is_active.is_(is_active))
        if priority_mode:
            statement = statement.where(MonitorProfile.priority_mode == priority_mode)
        if instant_alerts_enabled is not None:
            statement = statement.where(
                MonitorProfile.instant_alerts_enabled.is_(instant_alerts_enabled)
            )
        if digest_enabled is not None:
            statement = statement.where(MonitorProfile.digest_enabled.is_(digest_enabled))
        if search_query:
            statement = statement.where(
                text_search_clause(
                    search_query,
                    [
                        MonitorProfile.name,
                        MonitorProfile.category,
                        MonitorProfile.priority_mode,
                        Source.name,
                        TelegramChat.title,
                        TelegramUser.username,
                    ],
                )
            )
        statement = statement.order_by(desc(MonitorProfile.updated_at)).limit(limit)
        return list(self.session.scalars(statement).unique())

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
