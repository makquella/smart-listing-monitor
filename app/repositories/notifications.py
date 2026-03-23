from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.notification import NotificationLog


class NotificationRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, log: NotificationLog) -> NotificationLog:
        self.session.add(log)
        self.session.flush()
        return log

    def list_by_run(self, run_id: int) -> Sequence[NotificationLog]:
        statement = (
            select(NotificationLog)
            .where(NotificationLog.run_id == run_id)
            .order_by(desc(NotificationLog.sent_at))
        )
        return list(self.session.scalars(statement))
