from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DetectedEvent(Base):
    __tablename__ = "detected_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id"), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    old_value_json: Mapped[dict | None] = mapped_column(JSON)
    new_value_json: Mapped[dict | None] = mapped_column(JSON)
    changed_fields_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suppressed_reason: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
