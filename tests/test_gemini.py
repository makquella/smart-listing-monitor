import httpx
import pytest

from app.core.config import Settings
from app.models.event import DetectedEvent
from app.models.run import MonitoringRun
from app.models.source import Source
from app.services import gemini as gemini_module
from app.services.gemini import GeminiService


def _build_source() -> Source:
    return Source(
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


def _build_run() -> MonitoringRun:
    return MonitoringRun(
        id=1,
        source_id=1,
        trigger_type="manual",
        status="succeeded",
        started_at=None,
        finished_at=None,
        duration_ms=1000,
        pages_fetched=1,
        items_parsed=1,
        new_items_count=1,
        changed_items_count=0,
        removed_items_count=0,
        events_count=1,
        alerts_sent_count=0,
        parse_completeness_ratio=1.0,
        health_evaluation="healthy",
        error_message=None,
        created_at=None,
    )


def _build_event() -> DetectedEvent:
    return DetectedEvent(
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


def _service(api_key: str = "gemini-key") -> GeminiService:
    return GeminiService(Settings(gemini_api_key=api_key))


def _response(status_code: int, payload=None, *, content: bytes | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://example.com/gemini")
    if content is not None:
        return httpx.Response(status_code, content=content, request=request)
    return httpx.Response(status_code, json=payload, request=request)


def test_gemini_skips_when_no_events() -> None:
    result = _service().summarize_run(_build_source(), _build_run(), [])

    assert result.status == "skipped_no_events"
    assert result.highlights == []
    assert result.raw_response["error_kind"] == "no_events"


def test_gemini_falls_back_without_api_key() -> None:
    result = _service(api_key="").summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "skipped_no_api_key"
    assert result.highlights
    assert result.raw_response["error_kind"] == "no_api_key"


def test_gemini_returns_generated_summary_on_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(**_: object) -> httpx.Response:
        return _response(
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"summary_text":"AI summary","highlights":'
                                        '[{"title":"Price drop","severity":"high","why_it_matters":"Important"}]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(gemini_module, "request_with_retry", fake_request)

    result = _service().summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "generated"
    assert result.summary_text == "AI summary"
    assert result.highlights == [
        {
            "title": "Price drop",
            "severity": "high",
            "why_it_matters": "Important",
        }
    ]
    assert result.raw_response["status_code"] == 200
    assert "provider_response" in result.raw_response


def test_gemini_normalizes_missing_optional_highlight_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(**_: object) -> httpx.Response:
        return _response(
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"summary_text":"AI summary","highlights":'
                                        '[{"title":"New item"},{"title":"Another","severity":"urgent"}]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(gemini_module, "request_with_retry", fake_request)

    result = _service().summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "generated"
    assert result.highlights[0]["severity"] == "medium"
    assert result.highlights[0]["why_it_matters"]
    assert result.highlights[1]["severity"] == "medium"


def test_gemini_marks_auth_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(**_: object) -> httpx.Response:
        return _response(401, {"error": {"message": "bad key"}})

    monkeypatch.setattr(gemini_module, "request_with_retry", fake_request)

    result = _service().summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "auth_error"
    assert result.raw_response["error_kind"] == "auth_error"
    assert result.raw_response["status_code"] == 401
    assert "provider_response" in result.raw_response


def test_gemini_marks_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(**_: object) -> httpx.Response:
        return _response(429, {"error": {"message": "slow down"}})

    monkeypatch.setattr(gemini_module, "request_with_retry", fake_request)

    result = _service().summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "rate_limited"
    assert result.raw_response["error_kind"] == "rate_limited"
    assert result.raw_response["status_code"] == 429


def test_gemini_marks_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(**_: object) -> httpx.Response:
        return _response(503, {"error": {"message": "unavailable"}})

    monkeypatch.setattr(gemini_module, "request_with_retry", fake_request)

    result = _service().summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "provider_error"
    assert result.raw_response["error_kind"] == "provider_error"
    assert result.raw_response["status_code"] == 503


def test_gemini_marks_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(**_: object) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(gemini_module, "request_with_retry", fake_request)

    result = _service().summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "timeout"
    assert result.raw_response["error_kind"] == "timeout"


def test_gemini_marks_invalid_provider_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(**_: object) -> httpx.Response:
        return _response(200, content=b"not-json")

    monkeypatch.setattr(gemini_module, "request_with_retry", fake_request)

    result = _service().summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "invalid_response"
    assert result.raw_response["error_kind"] == "invalid_json"


def test_gemini_marks_invalid_response_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(**_: object) -> httpx.Response:
        return _response(200, {"candidates": []})

    monkeypatch.setattr(gemini_module, "request_with_retry", fake_request)

    result = _service().summarize_run(_build_source(), _build_run(), [_build_event()])

    assert result.status == "invalid_response"
    assert result.raw_response["error_kind"] == "invalid_response"
