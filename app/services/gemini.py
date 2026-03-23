import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.http import build_request_headers, request_with_retry, safe_response_json
from app.models.event import DetectedEvent
from app.models.run import MonitoringRun
from app.models.source import Source
from app.services.types import SummaryResult

logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"high", "medium", "low"}


@dataclass(slots=True)
class GeminiFailure:
    status: str
    error_kind: str
    safe_message: str
    status_code: int | None = None
    provider_payload: dict[str, Any] | None = None


class GeminiService:
    PROMPT_VERSION = "v1"

    def __init__(self, settings: Settings):
        self.settings = settings

    def summarize_run(
        self, source: Source, run: MonitoringRun, events: list[DetectedEvent]
    ) -> SummaryResult:
        top_events = events[:3]
        endpoint = self._endpoint()
        if not top_events:
            return SummaryResult(
                summary_text="No notable changes were detected in this run.",
                highlights=[],
                status="skipped_no_events",
                raw_response=self._skip_meta(
                    endpoint=endpoint,
                    error_kind="no_events",
                    message="No notable events were available for Gemini summarization.",
                ),
            )

        if not self.settings.gemini_api_key:
            return self._fallback_summary(
                top_events,
                status="skipped_no_api_key",
                raw_response=self._skip_meta(
                    endpoint=endpoint,
                    error_kind="no_api_key",
                    message="Gemini API key is not configured; deterministic fallback used.",
                ),
            )

        prompt_payload = {
            "source": source.name,
            "run_id": run.id,
            "run_status": run.status,
            "items_parsed": run.items_parsed,
            "events": [
                {
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "summary_text": event.summary_text,
                    "changed_fields": event.changed_fields_json,
                }
                for event in top_events
            ],
        }
        prompt = (
            "You are assisting an operator dashboard for a listing monitoring system.\n"
            "Return valid JSON with this exact shape: "
            '{"summary_text":"...", "highlights":[{"title":"...", "severity":"high|medium|low", "why_it_matters":"..."}]}.\n'
            "Keep the summary under 50 words. Keep 1 to 3 highlights.\n"
            f"Monitoring payload: {json.dumps(prompt_payload, ensure_ascii=True)}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
            },
        }
        headers = {
            "x-goog-api-key": self.settings.gemini_api_key,
            "Content-Type": "application/json",
        }
        try:
            response = request_with_retry(
                request_callable=httpx.post,
                logger=logger,
                service_name="gemini",
                method="POST",
                url=endpoint,
                timeout=self.settings.request_timeout_seconds,
                retry_attempts=self.settings.http_retry_attempts,
                retry_base_seconds=self.settings.http_retry_base_seconds,
                headers=build_request_headers(self.settings, headers),
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
            text = self._extract_response_text(payload)
            parsed = json.loads(text)
            summary_text = self._extract_summary_text(parsed)
            highlights = self._normalize_highlights(parsed.get("highlights"))
            if not summary_text and highlights:
                summary_text = (
                    f"Run completed with notable changes, led by {highlights[0]['title']}."
                )
            if not summary_text:
                raise ValueError("Gemini response did not include a usable summary_text.")
            return SummaryResult(
                summary_text=summary_text,
                highlights=highlights,
                status="generated",
                raw_response=self._success_meta(
                    endpoint=endpoint, response=response, payload=payload
                ),
            )
        except Exception as exc:  # pragma: no cover - behavior is tested via monkeypatching
            failure = self._classify_failure(exc)
            logger.warning(
                "Gemini summary generation degraded: status=%s error_kind=%s status_code=%s message=%s",
                failure.status,
                failure.error_kind,
                failure.status_code,
                failure.safe_message,
            )
            return self._fallback_summary(
                top_events,
                status=failure.status,
                raw_response=self._failure_meta(endpoint=endpoint, failure=failure),
            )

    def _fallback_summary(
        self, events: list[DetectedEvent], status: str, raw_response: dict[str, Any]
    ) -> SummaryResult:
        highlights = [
            {
                "title": event.summary_text,
                "severity": event.severity,
                "why_it_matters": self._why_it_matters(event),
            }
            for event in events[:3]
        ]
        summary_text = (
            f"{len(events)} notable update(s) detected, led by {events[0].summary_text.lower()}."
        )
        return SummaryResult(
            summary_text=summary_text,
            highlights=highlights,
            status=status,
            raw_response=raw_response,
        )

    def _endpoint(self) -> str:
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_model}:generateContent"
        )

    def _skip_meta(self, *, endpoint: str, error_kind: str, message: str) -> dict[str, Any]:
        return {
            "model": self.settings.gemini_model,
            "endpoint": endpoint,
            "error_kind": error_kind,
            "message": message,
        }

    def _success_meta(
        self, *, endpoint: str, response: httpx.Response, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "model": self.settings.gemini_model,
            "endpoint": endpoint,
            "status_code": response.status_code,
            "provider_response": payload,
        }

    def _failure_meta(self, *, endpoint: str, failure: GeminiFailure) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "model": self.settings.gemini_model,
            "endpoint": endpoint,
            "error_kind": failure.error_kind,
            "message": failure.safe_message,
        }
        if failure.status_code is not None:
            meta["status_code"] = failure.status_code
        if failure.provider_payload:
            meta["provider_response"] = failure.provider_payload
        return meta

    @staticmethod
    def _extract_response_text(payload: dict[str, Any]) -> str:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        if not isinstance(text, str) or not text.strip():
            raise TypeError("Gemini response text was empty or not a string.")
        return text

    @staticmethod
    def _extract_summary_text(parsed: dict[str, Any]) -> str:
        if not isinstance(parsed, dict):
            raise TypeError("Gemini JSON output must be an object.")
        summary_text = parsed.get("summary_text") or parsed.get("summary")
        if summary_text is None:
            return ""
        return str(summary_text).strip()

    @staticmethod
    def _normalize_highlights(payload: Any) -> list[dict[str, str]]:
        if not isinstance(payload, list):
            return []

        highlights: list[dict[str, str]] = []
        for entry in payload[:3]:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "").strip()
            if not title:
                continue
            severity = str(entry.get("severity") or "medium").lower().strip()
            if severity not in VALID_SEVERITIES:
                severity = "medium"
            why_it_matters = str(
                entry.get("why_it_matters")
                or entry.get("why")
                or "Gemini marked this update as operationally relevant."
            ).strip()
            highlights.append(
                {
                    "title": title,
                    "severity": severity,
                    "why_it_matters": why_it_matters,
                }
            )
        return highlights

    @staticmethod
    def _classify_failure(exc: Exception) -> GeminiFailure:
        if isinstance(exc, httpx.TimeoutException):
            return GeminiFailure(
                status="timeout",
                error_kind="timeout",
                safe_message="Gemini request timed out before a valid response was received.",
            )
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            status_code = response.status_code if response is not None else None
            provider_payload = safe_response_json(response)
            if status_code in {401, 403}:
                return GeminiFailure(
                    status="auth_error",
                    error_kind="auth_error",
                    safe_message="Gemini authentication failed. Check the configured API key.",
                    status_code=status_code,
                    provider_payload=provider_payload,
                )
            if status_code == 429:
                return GeminiFailure(
                    status="rate_limited",
                    error_kind="rate_limited",
                    safe_message="Gemini rate limit was reached. Retry after the provider cooldown.",
                    status_code=status_code,
                    provider_payload=provider_payload,
                )
            if status_code in {500, 502, 503, 504}:
                return GeminiFailure(
                    status="provider_error",
                    error_kind="provider_error",
                    safe_message="Gemini provider returned a server-side error.",
                    status_code=status_code,
                    provider_payload=provider_payload,
                )
            return GeminiFailure(
                status="provider_error",
                error_kind="provider_error",
                safe_message="Gemini request failed with a non-success HTTP status.",
                status_code=status_code,
                provider_payload=provider_payload,
            )
        if isinstance(exc, httpx.RequestError):
            return GeminiFailure(
                status="provider_error",
                error_kind="request_error",
                safe_message="Gemini request failed due to a network or transport error.",
            )
        if isinstance(exc, json.JSONDecodeError):
            return GeminiFailure(
                status="invalid_response",
                error_kind="invalid_json",
                safe_message="Gemini returned a response that could not be parsed as JSON.",
            )
        if isinstance(exc, (KeyError, IndexError, TypeError, ValueError)):
            return GeminiFailure(
                status="invalid_response",
                error_kind="invalid_response",
                safe_message="Gemini returned an unexpected response structure.",
            )
        return GeminiFailure(
            status="fallback",
            error_kind="unexpected_error",
            safe_message="Gemini summarization failed unexpectedly; deterministic fallback used.",
        )

    @staticmethod
    def _why_it_matters(event: DetectedEvent) -> str:
        if event.event_type == "availability_change":
            return "Availability shifts often require immediate attention."
        if event.event_type == "price_change":
            return "Meaningful price movement may signal a market or inventory update."
        if event.event_type == "new_item":
            return "New inventory changes the monitored catalogue."
        if event.event_type == "removed_item":
            return "An item disappearing may indicate sell-through or delisting."
        return "A key monitored field changed."
