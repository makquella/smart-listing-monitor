from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class MonitorProfile(Base):
    __tablename__ = "monitor_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), nullable=False, index=True)
    telegram_chat_id: Mapped[int] = mapped_column(ForeignKey("telegram_chats.id"), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(255))
    min_price: Mapped[float | None] = mapped_column(Float)
    max_price: Mapped[float | None] = mapped_column(Float)
    include_keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    exclude_keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    instant_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority_mode: Mapped[str] = mapped_column(String(32), default="high_medium", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    telegram_user = relationship("TelegramUser", back_populates="monitor_profiles")
    telegram_chat = relationship("TelegramChat", back_populates="monitor_profiles")
    source = relationship("Source")
    matches = relationship("MonitorMatch", back_populates="monitor_profile")
    notification_deliveries = relationship("NotificationDelivery", back_populates="monitor_profile")
