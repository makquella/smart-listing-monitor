from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_parsed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_items_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_items_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed_items_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alerts_sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parse_completeness_ratio: Mapped[float | None] = mapped_column()
    health_evaluation: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source = relationship("Source", back_populates="runs")
