from app.core.time import utcnow
from app.models.event import DetectedEvent
from app.models.item import Item
from app.models.monitor_profile import MonitorProfile
from app.models.run import MonitoringRun
from app.models.source import Source
from app.services.monitor_evaluator import MonitorEvaluator


def make_source() -> Source:
    now = utcnow()
    return Source(
        id=1,
        name="Books to Scrape",
        slug="books",
        parser_key="books_toscrape",
        base_url="https://books.toscrape.com/",
        start_url="https://books.toscrape.com/catalogue/page-1.html",
        schedule_enabled=True,
        schedule_interval_minutes=60,
        is_active=True,
        health_status="healthy",
        consecutive_failures=0,
        created_at=now,
        updated_at=now,
    )


def make_run() -> MonitoringRun:
    now = utcnow()
    return MonitoringRun(
        id=7,
        source_id=1,
        trigger_type="manual",
        status="succeeded",
        started_at=now,
        finished_at=now,
        duration_ms=4000,
        pages_fetched=1,
        items_parsed=25,
        new_items_count=1,
        changed_items_count=0,
        removed_items_count=0,
        events_count=1,
        alerts_sent_count=0,
        parse_completeness_ratio=1.0,
        health_evaluation="healthy",
        error_message=None,
        created_at=now,
    )


def make_profile(**overrides) -> MonitorProfile:
    now = utcnow()
    payload = {
        "id": 11,
        "telegram_user_id": 21,
        "telegram_chat_id": 31,
        "source_id": 1,
        "name": "Travel under 20",
        "is_active": True,
        "category": "Travel",
        "min_price": None,
        "max_price": 20.0,
        "include_keywords_json": ["guide"],
        "exclude_keywords_json": [],
        "instant_alerts_enabled": True,
        "digest_enabled": True,
        "priority_mode": "high_medium",
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return MonitorProfile(**payload)


def make_item(**overrides) -> Item:
    now = utcnow()
    payload = {
        "id": 101,
        "source_id": 1,
        "source_item_key": "travel-guide",
        "canonical_url": "https://books.toscrape.com/catalogue/travel-guide_1/index.html",
        "external_id": None,
        "title": "Europe Travel Guide",
        "currency": "GBP",
        "price_amount": 18.0,
        "availability_status": "in_stock",
        "rating": "Four",
        "attributes_json": {"category": "Travel"},
        "comparison_hash": "hash",
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": True,
        "missing_run_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return Item(**payload)


def make_event(**overrides) -> DetectedEvent:
    now = utcnow()
    payload = {
        "id": 201,
        "run_id": 7,
        "source_id": 1,
        "item_id": 101,
        "event_type": "new_item",
        "severity": "medium",
        "dedupe_key": "source:new_item:travel-guide",
        "old_value_json": None,
        "new_value_json": {"price_amount": 18.0, "availability_status": "in_stock"},
        "changed_fields_json": ["price_amount"],
        "summary_text": 'New item detected: "Europe Travel Guide" at GBP 18.00',
        "is_suppressed": False,
        "suppressed_reason": None,
        "created_at": now,
    }
    payload.update(overrides)
    return DetectedEvent(**payload)


def test_monitor_evaluator_matches_filters_and_promotes_priority() -> None:
    evaluator = MonitorEvaluator()
    source = make_source()
    run = make_run()
    profile = make_profile()
    item = make_item()
    event = make_event()

    matches = evaluator.evaluate(
        source=source,
        run=run,
        profiles=[profile],
        events=[event],
        items_by_id={item.id: item},
    )

    assert len(matches) == 1
    match = matches[0]
    assert match.draft.priority == "high"
    assert "category=Travel" in match.draft.match_reason
    assert "include=guide" in match.draft.match_reason
    assert evaluator.should_deliver(profile, match.draft.priority) is True


def test_monitor_evaluator_rejects_excluded_keywords_and_high_only_mode() -> None:
    evaluator = MonitorEvaluator()
    source = make_source()
    run = make_run()
    profile = make_profile(
        exclude_keywords_json=["damaged"],
        include_keywords_json=[],
        priority_mode="high_only",
        max_price=None,
    )
    item = make_item(title="Damaged Travel Notes")
    event = make_event(summary_text='Attribute change: "Damaged Travel Notes" rating updated', severity="low")

    matches = evaluator.evaluate(
        source=source,
        run=run,
        profiles=[profile],
        events=[event],
        items_by_id={item.id: item},
    )

    assert matches == []
    assert evaluator.should_deliver(profile, "high") is True
    assert evaluator.should_deliver(profile, "medium") is False
