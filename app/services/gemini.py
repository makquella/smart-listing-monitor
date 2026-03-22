import json
import logging

import httpx

from app.core.config import Settings
from app.models.event import DetectedEvent
from app.models.run import MonitoringRun
from app.models.source import Source
from app.services.types import SummaryResult


logger = logging.getLogger(__name__)


class GeminiService:
    PROMPT_VERSION = "v1"

    def __init__(self, settings: Settings):
        self.settings = settings

    def summarize_run(self, source: Source, run: MonitoringRun, events: list[DetectedEvent]) -> SummaryResult:
        top_events = events[:3]
        if not top_events:
            return SummaryResult(
                summary_text="No notable changes were detected in this run.",
                highlights=[],
                status="skipped",
                raw_response={},
            )

        if not self.settings.gemini_api_key:
            return self._fallback_summary(top_events, status="skipped")

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

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_model}:generateContent"
        )
        headers = {"x-goog-api-key": self.settings.gemini_api_key, "Content-Type": "application/json"}
        try:
            response = httpx.post(
                endpoint,
                headers=headers,
                json=body,
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            summary_text = parsed.get("summary_text") or "Run completed with notable changes."
            highlights = parsed.get("highlights") or []
            return SummaryResult(
                summary_text=summary_text,
                highlights=highlights[:3],
                status="generated",
                raw_response=payload,
            )
        except Exception:  # pragma: no cover - network failures are environment-specific
            logger.exception("Gemini summary generation failed, using fallback summary")
            return self._fallback_summary(top_events, status="fallback")

    def _fallback_summary(self, events: list[DetectedEvent], status: str) -> SummaryResult:
        highlights = [
            {
                "title": event.summary_text,
                "severity": event.severity,
                "why_it_matters": self._why_it_matters(event),
            }
            for event in events[:3]
        ]
        summary_text = f"{len(events)} notable update(s) detected, led by {events[0].summary_text.lower()}."
        return SummaryResult(
            summary_text=summary_text,
            highlights=highlights,
            status=status,
            raw_response={},
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
