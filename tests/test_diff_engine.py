from app.core.config import Settings
from app.core.time import utcnow
from app.models.item import Item
from app.services.diff_engine import DiffEngine
from app.services.normalization import NormalizationService
from app.services.types import ParsedItem


def build_item(**overrides) -> Item:
    now = utcnow()
    payload = {
        "id": 1,
        "source_id": 1,
        "source_item_key": "catalogue/book/index.html",
        "canonical_url": "https://books.toscrape.com/catalogue/book/index.html",
        "external_id": None,
        "title": "Book",
        "currency": "GBP",
        "price_amount": 10.0,
        "availability_status": "out_of_stock",
        "rating": "One",
        "attributes_json": {},
        "comparison_hash": "old",
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": True,
        "missing_run_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return Item(**payload)


def test_diff_engine_creates_high_priority_availability_event() -> None:
    settings = Settings()
    existing = build_item(availability_status="out_of_stock", comparison_hash="before")
    normalized = NormalizationService().normalize(
        type("Source", (), {"base_url": "https://books.toscrape.com/"})(),
        ParsedItem(
            canonical_url="catalogue/book/index.html",
            title="Book",
            price_amount=10.0,
            currency="GBP",
            availability_status="in_stock",
            rating="One",
        ),
    )

    event = DiffEngine(settings).compare(existing, normalized)

    assert event is not None
    assert event.event_type == "availability_change"
    assert "availability_status" in event.changed_fields


def test_diff_engine_ignores_small_price_delta() -> None:
    settings = Settings(MIN_ABSOLUTE_PRICE_DELTA=5.0, MIN_PERCENT_PRICE_DELTA=10.0)
    existing = build_item(price_amount=20.0, availability_status="in_stock", comparison_hash="before")
    normalized = NormalizationService().normalize(
        type("Source", (), {"base_url": "https://books.toscrape.com/"})(),
        ParsedItem(
            canonical_url="catalogue/book/index.html",
            title="Book",
            price_amount=20.5,
            currency="GBP",
            availability_status="in_stock",
            rating="One",
        ),
    )

    event = DiffEngine(settings).compare(existing, normalized)
    assert event is None
