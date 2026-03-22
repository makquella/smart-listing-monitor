from dataclasses import dataclass
import logging

import httpx

from app.core.config import Settings
from app.models.event import DetectedEvent
from app.models.item import Item
from app.models.run import MonitoringRun
from app.models.source import Source


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DeliveryResult:
    status: str
    provider_message_id: str | None = None
    error_message: str | None = None


class TelegramNotifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send_message(self, chat_id: str | int, message: str) -> DeliveryResult:
        return self._send_message(chat_id=chat_id, message=message)

    def send_event_alert(self, source: Source, run: MonitoringRun, event: DetectedEvent, item: Item | None) -> DeliveryResult:
        message = self.format_event_alert(source, run, event, item)
        destination = self.settings.telegram_chat_id or ""
        return self._send_message(chat_id=destination, message=message)

    def send_run_digest(
        self,
        *,
        source: Source,
        run: MonitoringRun,
        events: list[DetectedEvent],
        summary_text: str,
    ) -> DeliveryResult:
        message = self.format_run_digest(source=source, run=run, events=events, summary_text=summary_text)
        destination = self.settings.telegram_chat_id or ""
        return self._send_message(chat_id=destination, message=message)

    def send_failure_alert(self, source: Source, error_message: str) -> DeliveryResult:
        message = (
            f"[FAILING] {source.name}\n"
            f"Source transitioned into failing state.\n"
            f"Reason: {error_message}"
        )
        destination = self.settings.telegram_chat_id or ""
        return self._send_message(chat_id=destination, message=message)

    def format_event_alert(
        self,
        source: Source,
        run: MonitoringRun,
        event: DetectedEvent,
        item: Item | None,
    ) -> str:
        lines = [
            f"[{event.severity.upper()}] {source.name}",
            event.summary_text,
            f"Run: #{run.id}",
        ]
        if item is not None:
            lines.append(f"Link: {item.canonical_url}")
        return "\n".join(lines)

    def format_run_digest(
        self,
        *,
        source: Source,
        run: MonitoringRun,
        events: list[DetectedEvent],
        summary_text: str,
    ) -> str:
        top_events = events[:3]
        lines = [
            f"{source.name} run #{run.id} completed",
            f"Status: {run.status} in {round((run.duration_ms or 0) / 1000, 1)}s",
            (
                f"Items parsed: {run.items_parsed} | New: {run.new_items_count} | "
                f"Changed: {run.changed_items_count} | Removed: {run.removed_items_count}"
            ),
            "Top findings:",
        ]
        if top_events:
            for index, event in enumerate(top_events, start=1):
                lines.append(f"{index}. [{event.severity.upper()}] {event.summary_text}")
        else:
            lines.append("1. No unsuppressed findings")
        lines.extend(
            [
                "AI summary:",
                summary_text,
            ]
        )
        return "\n".join(lines)

    def _send_message(self, *, chat_id: str | int, message: str) -> DeliveryResult:
        if not self.settings.telegram_bot_token or not chat_id:
            return DeliveryResult(status="skipped", error_message="Telegram is not configured")

        endpoint = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": message,
            "disable_web_page_preview": True,
        }
        try:
            response = httpx.post(endpoint, json=payload, timeout=self.settings.request_timeout_seconds)
            response.raise_for_status()
            body = response.json()
            message_id = body.get("result", {}).get("message_id")
            return DeliveryResult(status="sent", provider_message_id=str(message_id) if message_id else None)
        except Exception as exc:  # pragma: no cover - network failures are environment-specific
            logger.exception("Failed to send Telegram notification")
            return DeliveryResult(status="failed", error_message=str(exc))
