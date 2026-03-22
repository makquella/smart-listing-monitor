from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime


class MonitorMatch(Base):
    __tablename__ = "monitor_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_profile_id: Mapped[int] = mapped_column(ForeignKey("monitor_profiles.id"), nullable=False, index=True)
    detected_event_id: Mapped[int] = mapped_column(ForeignKey("detected_events.id"), nullable=False, index=True)
    monitoring_run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id"), nullable=False, index=True)
    matched: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    match_reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    monitor_profile = relationship("MonitorProfile", back_populates="matches")
