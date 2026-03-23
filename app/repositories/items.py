from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.item import Item, ItemSnapshot
from app.services.types import NormalizedItem


class ItemRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, item_id: int) -> Item | None:
        return self.session.get(Item, item_id)

    def get_active_by_source(self, source_id: int) -> dict[str, Item]:
        statement = select(Item).where(Item.source_id == source_id, Item.is_active.is_(True))
        items = self.session.scalars(statement)
        return {item.source_item_key: item for item in items}

    def get_by_source(self, source_id: int) -> dict[str, Item]:
        statement = select(Item).where(Item.source_id == source_id)
        items = self.session.scalars(statement)
        return {item.source_item_key: item for item in items}

    def count_active_by_source(self, source_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(Item)
            .where(Item.source_id == source_id, Item.is_active.is_(True))
        )
        return int(self.session.scalar(statement) or 0)

    def list_recent(self, limit: int | None = None) -> Sequence[Item]:
        statement = select(Item).order_by(
            desc(Item.last_seen_at), desc(Item.updated_at), desc(Item.id)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_snapshots(self, item_id: int, limit: int = 20) -> Sequence[ItemSnapshot]:
        statement = (
            select(ItemSnapshot)
            .where(ItemSnapshot.item_id == item_id)
            .order_by(desc(ItemSnapshot.observed_at), desc(ItemSnapshot.id))
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def create_from_normalized(
        self, source_id: int, normalized: NormalizedItem, now: datetime
    ) -> Item:
        item = Item(
            source_id=source_id,
            source_item_key=normalized.source_item_key,
            canonical_url=normalized.canonical_url,
            external_id=normalized.external_id,
            title=normalized.title,
            currency=normalized.currency,
            price_amount=normalized.price_amount,
            availability_status=normalized.availability_status,
            rating=normalized.rating,
            attributes_json=normalized.attributes,
            comparison_hash=normalized.comparison_hash,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            missing_run_count=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def update_from_normalized(self, item: Item, normalized: NormalizedItem, now: datetime) -> Item:
        item.canonical_url = normalized.canonical_url
        item.external_id = normalized.external_id
        item.title = normalized.title
        item.currency = normalized.currency
        item.price_amount = normalized.price_amount
        item.availability_status = normalized.availability_status
        item.rating = normalized.rating
        item.attributes_json = normalized.attributes
        item.comparison_hash = normalized.comparison_hash
        item.last_seen_at = now
        item.is_active = True
        item.missing_run_count = 0
        item.updated_at = now
        self.session.add(item)
        self.session.flush()
        return item

    def increment_missing(self, item: Item, now: datetime) -> Item:
        item.missing_run_count += 1
        item.updated_at = now
        self.session.add(item)
        self.session.flush()
        return item

    def mark_removed(self, item: Item, now: datetime) -> Item:
        item.is_active = False
        item.updated_at = now
        self.session.add(item)
        self.session.flush()
        return item

    def create_snapshot(self, item: Item, run_id: int, now: datetime) -> ItemSnapshot:
        snapshot = ItemSnapshot(
            item_id=item.id,
            source_id=item.source_id,
            run_id=run_id,
            title=item.title,
            currency=item.currency,
            price_amount=item.price_amount,
            availability_status=item.availability_status,
            rating=item.rating,
            attributes_json=item.attributes_json,
            comparison_hash=item.comparison_hash,
            observed_at=now,
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot
