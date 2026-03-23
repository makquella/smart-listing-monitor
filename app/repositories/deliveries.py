from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.monitor_profile import MonitorProfile
from app.models.notification_delivery import NotificationDelivery
from app.models.source import Source
from app.models.telegram_chat import TelegramChat
from app.repositories.query_filters import text_search_clause


class NotificationDeliveryRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, delivery: NotificationDelivery) -> NotificationDelivery:
        self.session.add(delivery)
        self.session.flush()
        return delivery

    def list_recent(self, limit: int = 50) -> Sequence[NotificationDelivery]:
        statement = (
            select(NotificationDelivery)
            .order_by(desc(NotificationDelivery.created_at))
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_for_admin(
        self,
        *,
        limit: int = 80,
        status: str | None = None,
        delivery_type: str | None = None,
        monitor_profile_id: int | None = None,
        telegram_chat_id: int | None = None,
        source_id: int | None = None,
        monitoring_run_id: int | None = None,
        search_query: str | None = None,
    ) -> Sequence[NotificationDelivery]:
        statement = (
            select(NotificationDelivery)
            .outerjoin(
                MonitorProfile,
                MonitorProfile.id == NotificationDelivery.monitor_profile_id,
            )
            .outerjoin(TelegramChat, TelegramChat.id == NotificationDelivery.telegram_chat_id)
            .outerjoin(Source, Source.id == MonitorProfile.source_id)
        )
        if status:
            statement = statement.where(NotificationDelivery.status == status)
        if delivery_type:
            statement = statement.where(NotificationDelivery.delivery_type == delivery_type)
        if monitor_profile_id is not None:
            statement = statement.where(
                NotificationDelivery.monitor_profile_id == monitor_profile_id
            )
        if telegram_chat_id is not None:
            statement = statement.where(NotificationDelivery.telegram_chat_id == telegram_chat_id)
        if source_id is not None:
            statement = statement.where(MonitorProfile.source_id == source_id)
        if monitoring_run_id is not None:
            statement = statement.where(NotificationDelivery.monitoring_run_id == monitoring_run_id)
        if search_query:
            statement = statement.where(
                text_search_clause(
                    search_query,
                    [
                        NotificationDelivery.delivery_type,
                        NotificationDelivery.status,
                        NotificationDelivery.message_preview,
                        NotificationDelivery.error_text,
                        MonitorProfile.name,
                        TelegramChat.title,
                        Source.name,
                    ],
                )
            )
        statement = statement.order_by(desc(NotificationDelivery.created_at)).limit(limit)
        return list(self.session.scalars(statement).unique())

    def list_by_monitor(
        self, monitor_profile_id: int, limit: int = 50
    ) -> Sequence[NotificationDelivery]:
        statement = (
            select(NotificationDelivery)
            .where(NotificationDelivery.monitor_profile_id == monitor_profile_id)
            .order_by(desc(NotificationDelivery.created_at))
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_by_chat(
        self, telegram_chat_id: int, limit: int = 50
    ) -> Sequence[NotificationDelivery]:
        statement = (
            select(NotificationDelivery)
            .where(NotificationDelivery.telegram_chat_id == telegram_chat_id)
            .order_by(desc(NotificationDelivery.created_at))
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_by_run(self, monitoring_run_id: int) -> Sequence[NotificationDelivery]:
        statement = (
            select(NotificationDelivery)
            .where(NotificationDelivery.monitoring_run_id == monitoring_run_id)
            .order_by(desc(NotificationDelivery.created_at))
        )
        return list(self.session.scalars(statement))
