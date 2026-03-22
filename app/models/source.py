from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    parser_key: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    start_url: Mapped[str] = mapped_column(String(255), nullable=False)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schedule_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), default="healthy", nullable=False)
    last_run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failed_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items = relationship("Item", back_populates="source")
    runs = relationship("MonitoringRun", back_populates="source")
