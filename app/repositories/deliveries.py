from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.notification_delivery import NotificationDelivery


class NotificationDeliveryRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, delivery: NotificationDelivery) -> NotificationDelivery:
        self.session.add(delivery)
        self.session.flush()
        return delivery

    def list_recent(self, limit: int = 50) -> Sequence[NotificationDelivery]:
        statement = select(NotificationDelivery).order_by(desc(NotificationDelivery.created_at)).limit(limit)
        return list(self.session.scalars(statement))

    def list_by_monitor(self, monitor_profile_id: int, limit: int = 50) -> Sequence[NotificationDelivery]:
        statement = (
            select(NotificationDelivery)
            .where(NotificationDelivery.monitor_profile_id == monitor_profile_id)
            .order_by(desc(NotificationDelivery.created_at))
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_by_chat(self, telegram_chat_id: int, limit: int = 50) -> Sequence[NotificationDelivery]:
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
