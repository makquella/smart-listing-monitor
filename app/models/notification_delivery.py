from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_profile_id: Mapped[int] = mapped_column(ForeignKey("monitor_profiles.id"), nullable=False, index=True)
    telegram_chat_id: Mapped[int] = mapped_column(ForeignKey("telegram_chats.id"), nullable=False, index=True)
    detected_event_id: Mapped[int | None] = mapped_column(ForeignKey("detected_events.id"), index=True)
    monitoring_run_id: Mapped[int | None] = mapped_column(ForeignKey("monitoring_runs.id"), index=True)
    delivery_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message_preview: Mapped[str | None] = mapped_column(Text)
    telegram_message_id: Mapped[str | None] = mapped_column(String(120))
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    monitor_profile = relationship("MonitorProfile", back_populates="notification_deliveries")
    telegram_chat = relationship("TelegramChat", back_populates="notification_deliveries")
