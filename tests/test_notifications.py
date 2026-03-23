import httpx

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

    text = notifier.format_run_digest(
        source=source, run=run, events=[event], summary_text="AI summary text"
    )

    assert "AI summary:" in text
    assert "New item detected" in text


class FakeTelegramResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        headers: dict | None = None,
        text: str = "",
    ):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


def test_telegram_notifier_chunks_long_messages(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(url: str, json: dict, timeout: int, headers=None):
        calls.append(json)
        return FakeTelegramResponse(
            200,
            payload={"ok": True, "result": {"message_id": len(calls)}},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    notifier = TelegramNotifier(
        Settings(
            telegram_bot_token="token",
            telegram_chat_id="123",
            telegram_message_chunk_size=32,
        )
    )

    message = "Header\n" + "\n".join(f"line {index} with some content" for index in range(8))
    result = notifier.send_message("123", message)

    assert result.status == "sent"
    assert result.chunk_count > 1
    assert len(calls) == result.chunk_count
    assert all(len(call["text"]) <= 32 for call in calls)


def test_telegram_notifier_retries_on_429_and_5xx(monkeypatch) -> None:
    sleeps: list[float] = []
    responses = [
        FakeTelegramResponse(
            429,
            payload={
                "ok": False,
                "description": "Too Many Requests",
                "parameters": {"retry_after": 3},
            },
        ),
        FakeTelegramResponse(502, text="bad gateway"),
        FakeTelegramResponse(200, payload={"ok": True, "result": {"message_id": 99}}),
    ]

    def fake_post(url: str, json: dict, timeout: int, headers=None):
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.core.http.time.sleep", sleeps.append)

    notifier = TelegramNotifier(
        Settings(
            telegram_bot_token="token",
            telegram_chat_id="123",
            telegram_retry_attempts=4,
            telegram_retry_base_seconds=0.5,
        )
    )

    result = notifier.send_message("123", "hello")

    assert result.status == "sent"
    assert result.provider_message_id == "99"
    assert sleeps == [3.0, 1.0]
