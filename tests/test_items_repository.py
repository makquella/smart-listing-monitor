from datetime import UTC, datetime, timedelta

from app.models.event import DetectedEvent
from app.models.item import Item, ItemSnapshot
from app.models.source import Source
from app.repositories.events import EventRepository
from app.repositories.items import ItemRepository


def test_item_repository_lists_recent_items_and_snapshots(session_factory) -> None:
    with session_factory() as session:
        now = datetime.now(UTC)
        source = Source(
            name="Books",
            slug="books",
            parser_key="books_toscrape",
            base_url="https://example.com",
            start_url="https://example.com/catalogue",
            schedule_enabled=True,
            schedule_interval_minutes=60,
            is_active=True,
            health_status="healthy",
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        session.flush()

        older_item = Item(
            source_id=source.id,
            source_item_key="older",
            canonical_url="https://example.com/older",
            title="Older",
            currency="GBP",
            price_amount=10.0,
            availability_status="in_stock",
            rating="Two",
            attributes_json={},
            comparison_hash="older-hash",
            first_seen_at=now - timedelta(days=2),
            last_seen_at=now - timedelta(hours=2),
            is_active=True,
            missing_run_count=0,
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(hours=2),
        )
        newer_item = Item(
            source_id=source.id,
            source_item_key="newer",
            canonical_url="https://example.com/newer",
            title="Newer",
            currency="GBP",
            price_amount=20.0,
            availability_status="in_stock",
            rating="Five",
            attributes_json={},
            comparison_hash="newer-hash",
            first_seen_at=now - timedelta(days=1),
            last_seen_at=now,
            is_active=True,
            missing_run_count=0,
            created_at=now - timedelta(days=1),
            updated_at=now,
        )
        session.add_all([older_item, newer_item])
        session.flush()

        session.add_all(
            [
                ItemSnapshot(
                    item_id=newer_item.id,
                    source_id=source.id,
                    run_id=1,
                    title="Newer",
                    currency="GBP",
                    price_amount=19.0,
                    availability_status="in_stock",
                    rating="Four",
                    attributes_json={},
                    comparison_hash="snap-1",
                    observed_at=now - timedelta(hours=3),
                ),
                ItemSnapshot(
                    item_id=newer_item.id,
                    source_id=source.id,
                    run_id=2,
                    title="Newer",
                    currency="GBP",
                    price_amount=20.0,
                    availability_status="in_stock",
                    rating="Five",
                    attributes_json={},
                    comparison_hash="snap-2",
                    observed_at=now - timedelta(hours=1),
                ),
            ]
        )
        session.commit()

        repo = ItemRepository(session)
        items = repo.list_recent()
        snapshots = repo.list_snapshots(newer_item.id)

        assert items[0].id == newer_item.id
        assert items[1].id == older_item.id
        assert snapshots[0].run_id == 2
        assert snapshots[1].run_id == 1
        assert repo.get(newer_item.id).title == "Newer"


def test_event_repository_lists_recent_events_by_item(session_factory) -> None:
    with session_factory() as session:
        now = datetime.now(UTC)
        source = Source(
            name="Books",
            slug="books-events",
            parser_key="books_toscrape",
            base_url="https://example.com",
            start_url="https://example.com/catalogue",
            schedule_enabled=True,
            schedule_interval_minutes=60,
            is_active=True,
            health_status="healthy",
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        session.flush()

        item = Item(
            source_id=source.id,
            source_item_key="tracked",
            canonical_url="https://example.com/tracked",
            title="Tracked",
            currency="GBP",
            price_amount=30.0,
            availability_status="in_stock",
            rating="Three",
            attributes_json={},
            comparison_hash="tracked-hash",
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            missing_run_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        session.flush()

        other_item = Item(
            source_id=source.id,
            source_item_key="other",
            canonical_url="https://example.com/other",
            title="Other",
            currency="GBP",
            price_amount=18.0,
            availability_status="in_stock",
            rating="One",
            attributes_json={},
            comparison_hash="other-hash",
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            missing_run_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add(other_item)
        session.flush()

        session.add_all(
            [
                DetectedEvent(
                    run_id=1,
                    source_id=source.id,
                    item_id=item.id,
                    event_type="price_change",
                    severity="medium",
                    dedupe_key="tracked-price",
                    old_value_json={"price_amount": 35.0},
                    new_value_json={"price_amount": 30.0},
                    changed_fields_json=["price_amount"],
                    summary_text="Tracked item price changed",
                    is_suppressed=False,
                    created_at=now - timedelta(minutes=5),
                ),
                DetectedEvent(
                    run_id=2,
                    source_id=source.id,
                    item_id=item.id,
                    event_type="availability_change",
                    severity="high",
                    dedupe_key="tracked-stock",
                    old_value_json={"availability_status": "out_of_stock"},
                    new_value_json={"availability_status": "in_stock"},
                    changed_fields_json=["availability_status"],
                    summary_text="Tracked item returned to stock",
                    is_suppressed=False,
                    created_at=now,
                ),
                DetectedEvent(
                    run_id=3,
                    source_id=source.id,
                    item_id=other_item.id,
                    event_type="new_item",
                    severity="medium",
                    dedupe_key="other-new",
                    old_value_json=None,
                    new_value_json={"title": "Other"},
                    changed_fields_json=["title"],
                    summary_text="Other item detected",
                    is_suppressed=False,
                    created_at=now + timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

        events = EventRepository(session).list_recent_by_item(item.id)

        assert len(events) == 2
        assert events[0].event_type == "availability_change"
        assert events[1].event_type == "price_change"
