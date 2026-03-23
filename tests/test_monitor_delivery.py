from app.core.time import utcnow
from app.models.event import DetectedEvent
from app.models.item import Item
from app.models.notification_delivery import NotificationDelivery
from app.models.run import MonitoringRun
from app.models.source import Source
from app.repositories.deliveries import NotificationDeliveryRepository
from app.repositories.monitor_matches import MonitorMatchRepository
from app.services.monitor_evaluator import EvaluatedMonitorMatch, MonitorEvaluator
from app.services.monitor_profiles import MonitorProfileService
from app.services.telegram import DeliveryResult
from app.services.telegram_notifier import MonitorTelegramNotifier
from app.services.types import MonitorMatchDraft, MonitorProfileCreate


class FakeTelegramNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[int | str, str]] = []

    def send_message(self, chat_id: int | str, message: str) -> DeliveryResult:
        self.messages.append((chat_id, message))
        return DeliveryResult(status="sent", provider_message_id=str(len(self.messages)))


def seed_source_and_profile(session_factory):
    with session_factory() as session:
        now = utcnow()
        source = Source(
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
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        source_id = source.id

    profile = MonitorProfileService(session_factory).create(
        MonitorProfileCreate(
            telegram_user_external_id=9001,
            telegram_chat_external_id=7001,
            chat_type="private",
            username="monitor_user",
            first_name="Monitor",
            last_name="User",
            chat_title=None,
            source_id=source_id,
            name="Travel under 20",
            category="Travel",
            max_price=20.0,
            include_keywords=["guide"],
            instant_alerts_enabled=True,
            digest_enabled=True,
            priority_mode="all",
        )
    )
    return source_id, profile


def seed_run_event(session_factory, *, source_id: int, suppressed: bool = False):
    with session_factory() as session:
        now = utcnow()
        run = MonitoringRun(
            source_id=source_id,
            trigger_type="manual",
            status="succeeded",
            started_at=now,
            finished_at=now,
            duration_ms=3500,
            pages_fetched=1,
            items_parsed=12,
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
        session.add(run)
        session.flush()

        item = Item(
            source_id=source_id,
            source_item_key="travel-guide",
            canonical_url="https://books.toscrape.com/catalogue/travel-guide_1/index.html",
            external_id=None,
            title="Europe Travel Guide",
            currency="GBP",
            price_amount=18.0,
            availability_status="in_stock",
            rating="Four",
            attributes_json={"category": "Travel"},
            comparison_hash="hash",
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            missing_run_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        session.flush()

        event = DetectedEvent(
            run_id=run.id,
            source_id=source_id,
            item_id=item.id,
            event_type="new_item",
            severity="medium",
            dedupe_key="books:new_item:travel-guide",
            old_value_json=None,
            new_value_json={"price_amount": 18.0, "availability_status": "in_stock"},
            changed_fields_json=["price_amount"],
            summary_text='New item detected: "Europe Travel Guide" at GBP 18.00',
            is_suppressed=suppressed,
            suppressed_reason="Cooldown active" if suppressed else None,
            created_at=now,
        )
        session.add(event)
        session.commit()
        session.refresh(run)
        session.refresh(item)
        session.refresh(event)
        source = session.get(Source, source_id)
        assert source is not None
        return source, run, item, event


def test_monitor_notifier_persists_matches_and_sends_instant_and_digest(session_factory) -> None:
    source_id, profile = seed_source_and_profile(session_factory)
    source, run, item, event = seed_run_event(session_factory, source_id=source_id)
    fake_notifier = FakeTelegramNotifier()
    notifier = MonitorTelegramNotifier(
        session_factory=session_factory,
        notifier=fake_notifier,
        evaluator=MonitorEvaluator(),
    )
    match = EvaluatedMonitorMatch(
        draft=MonitorMatchDraft(
            monitor_profile_id=profile.id,
            detected_event_id=event.id,
            monitoring_run_id=run.id,
            matched=True,
            match_reason="category=Travel; include=guide; price=18.00; event=new_item",
            priority="high",
        ),
        profile=profile,
        event=event,
        item=item,
    )

    persisted = notifier.persist_matches([match])
    sent_count = notifier.deliver(
        source=source,
        run=run,
        summary=type(
            "Summary", (), {"summary_text": "Travel monitor found one high-priority match."}
        )(),
        matches=[match],
    )

    assert len(persisted) == 1
    assert sent_count == 2
    assert len(fake_notifier.messages) == 2
    assert fake_notifier.messages[0][0] == 7001
    assert "Why matched" in fake_notifier.messages[0][1]
    assert "Monitoring Digest" in fake_notifier.messages[1][1]

    with session_factory() as session:
        matches = list(MonitorMatchRepository(session).list_by_monitor(profile.id))
        deliveries = list(NotificationDeliveryRepository(session).list_by_monitor(profile.id))

    assert len(matches) == 1
    assert len(deliveries) == 2
    assert {delivery.delivery_type for delivery in deliveries} == {"instant", "digest"}
    assert {delivery.status for delivery in deliveries} == {"sent"}


def test_monitor_notifier_logs_suppressed_events_without_sending_digest(session_factory) -> None:
    source_id, profile = seed_source_and_profile(session_factory)
    source, run, item, event = seed_run_event(session_factory, source_id=source_id, suppressed=True)
    fake_notifier = FakeTelegramNotifier()
    notifier = MonitorTelegramNotifier(
        session_factory=session_factory,
        notifier=fake_notifier,
        evaluator=MonitorEvaluator(),
    )
    match = EvaluatedMonitorMatch(
        draft=MonitorMatchDraft(
            monitor_profile_id=profile.id,
            detected_event_id=event.id,
            monitoring_run_id=run.id,
            matched=True,
            match_reason="category=Travel; event=new_item; platform_suppressed",
            priority="high",
        ),
        profile=profile,
        event=event,
        item=item,
    )

    notifier.persist_matches([match])
    sent_count = notifier.deliver(
        source=source,
        run=run,
        summary=type("Summary", (), {"summary_text": "Suppressed change."})(),
        matches=[match],
    )

    assert sent_count == 0
    assert fake_notifier.messages == []

    with session_factory() as session:
        deliveries = list(NotificationDeliveryRepository(session).list_by_monitor(profile.id))

    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert isinstance(delivery, NotificationDelivery)
    assert delivery.delivery_type == "instant"
    assert delivery.status == "suppressed"
