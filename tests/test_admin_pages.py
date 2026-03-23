from datetime import timedelta

import pytest
from fastapi import Request

from app.core.time import utcnow
from app.models.ai_summary import AISummary
from app.models.event import DetectedEvent
from app.models.item import Item
from app.models.monitor_match import MonitorMatch
from app.models.monitor_profile import MonitorProfile
from app.models.notification_delivery import NotificationDelivery
from app.models.run import MonitoringRun
from app.models.source import Source
from app.models.telegram_chat import TelegramChat
from app.models.telegram_user import TelegramUser
from app.web.page_builders import (
    build_deliveries_page,
    build_findings_page,
    build_monitors_page,
    build_runs_page,
)
from app.web.params import (
    DeliveriesPageParams,
    FindingsPageParams,
    MonitorsPageParams,
    RunsPageParams,
)


def _make_request(path: str, query_string: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": query_string.encode(),
            "headers": [],
        }
    )


@pytest.fixture()
def admin_dataset(session_factory) -> dict[str, int]:
    with session_factory() as session:
        now = utcnow()

        books = Source(
            name="Books to Scrape",
            slug="books-to-scrape",
            parser_key="books_toscrape",
            base_url="https://books.toscrape.com/",
            start_url="https://books.toscrape.com/catalogue/page-1.html",
            schedule_enabled=True,
            schedule_interval_minutes=60,
            is_active=True,
            health_status="healthy",
            consecutive_failures=0,
            created_at=now - timedelta(days=14),
            updated_at=now - timedelta(hours=1),
        )
        phones = Source(
            name="Web Scraper Phones",
            slug="web-scraper-phones",
            parser_key="webscraper_static_ecommerce",
            base_url="https://webscraper.io/",
            start_url="https://webscraper.io/test-sites/e-commerce/static/computers/phones",
            schedule_enabled=True,
            schedule_interval_minutes=30,
            is_active=True,
            health_status="degraded",
            consecutive_failures=1,
            created_at=now - timedelta(days=7),
            updated_at=now - timedelta(hours=2),
        )
        session.add_all([books, phones])
        session.flush()

        run_books = MonitoringRun(
            source_id=books.id,
            trigger_type="manual",
            status="succeeded",
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1) + timedelta(seconds=8),
            duration_ms=8_000,
            pages_fetched=4,
            items_parsed=1000,
            new_items_count=3,
            changed_items_count=1,
            removed_items_count=0,
            events_count=2,
            alerts_sent_count=1,
            parse_completeness_ratio=1.0,
            health_evaluation="healthy",
            error_message=None,
            created_at=now - timedelta(hours=1),
        )
        run_phones = MonitoringRun(
            source_id=phones.id,
            trigger_type="telegram_manual",
            status="failed",
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=2) + timedelta(seconds=14),
            duration_ms=14_000,
            pages_fetched=1,
            items_parsed=12,
            new_items_count=0,
            changed_items_count=0,
            removed_items_count=0,
            events_count=1,
            alerts_sent_count=0,
            parse_completeness_ratio=0.4,
            health_evaluation="failing",
            error_message="Timeout while loading page",
            created_at=now - timedelta(hours=2),
        )
        session.add_all([run_books, run_phones])
        session.flush()

        travel_item = Item(
            source_id=books.id,
            source_item_key="travel-guide",
            canonical_url="https://books.toscrape.com/catalogue/travel-guide_1/index.html",
            external_id=None,
            title="Travel Guide Deluxe",
            currency="GBP",
            price_amount=18.0,
            availability_status="in_stock",
            rating="Four",
            attributes_json={"category": "Travel"},
            comparison_hash="travel-hash",
            first_seen_at=now - timedelta(days=2),
            last_seen_at=now - timedelta(hours=1),
            is_active=True,
            missing_run_count=0,
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(hours=1),
        )
        phone_item = Item(
            source_id=phones.id,
            source_item_key="phone-alpha",
            canonical_url="https://webscraper.io/test-sites/e-commerce/static/product/1",
            external_id=None,
            title="Phone Alpha",
            currency="USD",
            price_amount=199.99,
            availability_status="out_of_stock",
            rating="Three",
            attributes_json={"category": "Phones"},
            comparison_hash="phone-hash",
            first_seen_at=now - timedelta(days=1),
            last_seen_at=now - timedelta(hours=2),
            is_active=True,
            missing_run_count=0,
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(hours=2),
        )
        session.add_all([travel_item, phone_item])
        session.flush()

        travel_event = DetectedEvent(
            run_id=run_books.id,
            source_id=books.id,
            item_id=travel_item.id,
            event_type="price_change",
            severity="high",
            dedupe_key="books:price_change:travel-guide",
            old_value_json={"price_amount": 24.0},
            new_value_json={"price_amount": 18.0},
            changed_fields_json=["price_amount"],
            summary_text="Travel Guide Deluxe price dropped from GBP 24.00 to GBP 18.00",
            is_suppressed=False,
            suppressed_reason=None,
            created_at=now - timedelta(minutes=55),
        )
        phone_event = DetectedEvent(
            run_id=run_phones.id,
            source_id=phones.id,
            item_id=phone_item.id,
            event_type="availability_change",
            severity="medium",
            dedupe_key="phones:availability_change:phone-alpha",
            old_value_json={"availability_status": "in_stock"},
            new_value_json={"availability_status": "out_of_stock"},
            changed_fields_json=["availability_status"],
            summary_text="Phone Alpha went out of stock",
            is_suppressed=True,
            suppressed_reason="Cooldown active",
            created_at=now - timedelta(hours=2),
        )
        session.add_all([travel_event, phone_event])
        session.flush()

        telegram_user = TelegramUser(
            telegram_user_id=9001,
            username="traveler",
            first_name="Travel",
            last_name="Watcher",
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(hours=1),
        )
        telegram_chat = TelegramChat(
            telegram_chat_id=7001,
            chat_type="private",
            title="Travel Alerts",
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(hours=1),
        )
        session.add_all([telegram_user, telegram_chat])
        session.flush()

        travel_monitor = MonitorProfile(
            telegram_user_id=telegram_user.id,
            telegram_chat_id=telegram_chat.id,
            source_id=books.id,
            name="Travel under 20",
            is_active=True,
            category="Travel",
            min_price=None,
            max_price=20.0,
            include_keywords_json=["guide"],
            exclude_keywords_json=[],
            instant_alerts_enabled=True,
            digest_enabled=True,
            priority_mode="high_medium",
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(minutes=40),
        )
        dormant_monitor = MonitorProfile(
            telegram_user_id=telegram_user.id,
            telegram_chat_id=telegram_chat.id,
            source_id=phones.id,
            name="Phones watcher",
            is_active=False,
            category="Phones",
            min_price=None,
            max_price=400.0,
            include_keywords_json=[],
            exclude_keywords_json=[],
            instant_alerts_enabled=False,
            digest_enabled=True,
            priority_mode="all",
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(hours=3),
        )
        session.add_all([travel_monitor, dormant_monitor])
        session.flush()

        travel_match = MonitorMatch(
            monitor_profile_id=travel_monitor.id,
            detected_event_id=travel_event.id,
            monitoring_run_id=run_books.id,
            matched=True,
            match_reason="category=Travel; include=guide; price=18.00; event=price_change",
            priority="high",
            created_at=now - timedelta(minutes=54),
        )
        session.add(travel_match)

        sent_delivery = NotificationDelivery(
            monitor_profile_id=travel_monitor.id,
            telegram_chat_id=telegram_chat.id,
            detected_event_id=travel_event.id,
            monitoring_run_id=run_books.id,
            delivery_type="instant",
            status="sent",
            message_preview="High Priority — Travel Guide Deluxe now costs GBP 18.00",
            telegram_message_id="100",
            error_text=None,
            created_at=now - timedelta(minutes=53),
            sent_at=now - timedelta(minutes=53),
        )
        failed_delivery = NotificationDelivery(
            monitor_profile_id=dormant_monitor.id,
            telegram_chat_id=telegram_chat.id,
            detected_event_id=phone_event.id,
            monitoring_run_id=run_phones.id,
            delivery_type="digest",
            status="failed",
            message_preview="Phone Alpha went out of stock",
            telegram_message_id=None,
            error_text="Chat not reachable",
            created_at=now - timedelta(hours=2),
            sent_at=None,
        )
        summary = AISummary(
            run_id=run_books.id,
            source_id=books.id,
            model_name="gemini-2.5-flash",
            prompt_version="v1",
            summary_text="Travel pricing changed and produced one high-priority alert.",
            highlights_json=[{"title": "Travel Guide Deluxe", "why": "Below target price"}],
            status="generated",
            response_json={"status": "ok"},
            created_at=now - timedelta(minutes=50),
        )
        session.add_all([sent_delivery, failed_delivery, summary])
        session.commit()

        return {
            "books_source_id": books.id,
            "phones_source_id": phones.id,
            "books_run_id": run_books.id,
            "travel_event_id": travel_event.id,
            "travel_monitor_id": travel_monitor.id,
            "telegram_chat_id": telegram_chat.id,
        }


def test_runs_page_builder_filters_runs_and_computes_quality(
    session_factory, admin_dataset
) -> None:
    with session_factory() as session:
        page = build_runs_page(
            session,
            RunsPageParams(
                search_query="books",
                status="succeeded",
                trigger_type="manual",
                source_id=admin_dataset["books_source_id"],
            ),
        )

    assert [run.id for run in page["runs"]] == [admin_dataset["books_run_id"]]
    assert page["run_stats"]["succeeded"] == 1
    assert page["run_stats"]["failed"] == 0
    assert page["run_quality"]["last_run"] is not None
    assert page["run_quality"]["fastest_run"] is not None


def test_findings_page_builder_uses_filtered_query_results(session_factory, admin_dataset) -> None:
    with session_factory() as session:
        page = build_findings_page(
            session,
            FindingsPageParams(
                search_query="travel",
                run_id=None,
                severity="high",
                event_type=None,
                source_id=admin_dataset["books_source_id"],
                suppressed=False,
            ),
        )

    assert [event.id for event in page["events"]] == [admin_dataset["travel_event_id"]]
    assert page["finding_stats"]["high"] == 1
    assert page["finding_stats"]["suppressed"] == 0
    assert "price_change" in page["finding_filters"]["event_types"]


def test_monitors_page_builder_shapes_activity_without_fastapi(
    session_factory, admin_dataset
) -> None:
    with session_factory() as session:
        page = build_monitors_page(
            session,
            MonitorsPageParams(
                search_query="travel",
                source_id=admin_dataset["books_source_id"],
                is_active=True,
                priority_mode=None,
                instant_alerts_enabled=True,
                digest_enabled=True,
            ),
        )

    assert len(page["profiles"]) == 1
    profile = page["profiles"][0]
    activity = page["profile_activity"][profile.id]
    assert profile.id == admin_dataset["travel_monitor_id"]
    assert activity["matches_24h"] == 1
    assert activity["deliveries_7d"] == 1
    assert page["monitor_stats"]["active"] == 1
    assert page["recent_matches"]


def test_deliveries_page_builder_filters_and_populates_filter_lists(
    session_factory, admin_dataset
) -> None:
    with session_factory() as session:
        page = build_deliveries_page(
            session,
            DeliveriesPageParams(
                search_query="travel",
                status="sent",
                delivery_type="instant",
                monitor_profile_id=admin_dataset["travel_monitor_id"],
                telegram_chat_id=admin_dataset["telegram_chat_id"],
                source_id=admin_dataset["books_source_id"],
                monitoring_run_id=admin_dataset["books_run_id"],
            ),
        )

    assert len(page["deliveries"]) == 1
    delivery = page["deliveries"][0]
    assert delivery.status == "sent"
    assert delivery.delivery_type == "instant"
    assert page["delivery_stats"]["sent"] == 1
    assert page["delivery_filters"]["profiles"]
    assert page["delivery_filters"]["sources"]


def test_runs_page_params_parse_request_query() -> None:
    request = _make_request(
        "/admin/runs", "q=travel&status=failed&trigger=telegram_manual&source_id=2"
    )

    params = RunsPageParams.from_request(request)

    assert params.search_query == "travel"
    assert params.status == "failed"
    assert params.trigger_type == "telegram_manual"
    assert params.source_id == 2
