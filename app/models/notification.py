from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("monitoring_runs.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("detected_events.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    destination: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(120))
    payload_preview: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
