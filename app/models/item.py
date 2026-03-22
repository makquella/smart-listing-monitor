from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source_id", "source_item_key", name="uq_source_item_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True, nullable=False)
    source_item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(500), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), default="GBP", nullable=False)
    price_amount: Mapped[float | None] = mapped_column(Float)
    availability_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    rating: Mapped[str | None] = mapped_column(String(32))
    attributes_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    comparison_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    missing_run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    source = relationship("Source", back_populates="items")
    snapshots = relationship("ItemSnapshot", back_populates="item")


class ItemSnapshot(Base):
    __tablename__ = "item_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), default="GBP", nullable=False)
    price_amount: Mapped[float | None] = mapped_column(Float)
    availability_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    rating: Mapped[str | None] = mapped_column(String(32))
    attributes_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    comparison_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    item = relationship("Item", back_populates="snapshots")
