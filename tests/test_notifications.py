from app.core.config import Settings
from app.models.event import DetectedEvent
from app.models.run import MonitoringRun
from app.models.source import Source
from app.services.telegram import TelegramNotifier


def test_telegram_notifier_skips_when_not_configured() -> None:
    notifier = TelegramNotifier(Settings(telegram_bot_token="", telegram_chat_id=""))
    result = notifier.send_failure_alert(
        Source(
            id=1,
            name="Source",
            slug="source",
            parser_key="fake",
            base_url="https://example.com",
            start_url="https://example.com",
            schedule_enabled=True,
            schedule_interval_minutes=60,
            is_active=True,
            health_status="healthy",
            consecutive_failures=0,
            created_at=None,
            updated_at=None,
        ),
        "boom",
    )
    assert result.status == "skipped"


def test_telegram_digest_format_includes_summary() -> None:
    notifier = TelegramNotifier(Settings())
    source = Source(
        id=1,
        name="Source",
        slug="source",
        parser_key="fake",
        base_url="https://example.com",
        start_url="https://example.com",
        schedule_enabled=True,
        schedule_interval_minutes=60,
        is_active=True,
        health_status="healthy",
        consecutive_failures=0,
        created_at=None,
        updated_at=None,
    )
    run = MonitoringRun(
        id=1,
        source_id=1,
        trigger_type="manual",
        status="succeeded",
        started_at=None,
        finished_at=None,
        duration_ms=5000,
        pages_fetched=1,
        items_parsed=10,
        new_items_count=1,
        changed_items_count=2,
        removed_items_count=0,
        events_count=3,
        alerts_sent_count=0,
        parse_completeness_ratio=1.0,
        health_evaluation="healthy",
        error_message=None,
        created_at=None,
    )
    event = DetectedEvent(
        id=1,
        run_id=1,
        source_id=1,
        item_id=1,
        event_type="new_item",
        severity="medium",
        dedupe_key="k",
        old_value_json=None,
        new_value_json={},
        changed_fields_json=[],
        summary_text="New item detected",
        is_suppressed=False,
        suppressed_reason=None,
        created_at=None,
    )

    text = notifier.format_run_digest(source=source, run=run, events=[event], summary_text="AI summary text")

    assert "AI summary:" in text
    assert "New item detected" in text
