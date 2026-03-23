import logging
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.http import (
    build_request_headers,
    request_with_retry,
    safe_response_json,
)
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
    chunk_count: int = 0


class TelegramNotifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send_message(self, chat_id: str | int, message: str) -> DeliveryResult:
        return self._send_message(chat_id=chat_id, message=message)

    def send_event_alert(
        self, source: Source, run: MonitoringRun, event: DetectedEvent, item: Item | None
    ) -> DeliveryResult:
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
        message = self.format_run_digest(
            source=source, run=run, events=events, summary_text=summary_text
        )
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
            return DeliveryResult(
                status="skipped", error_message="Telegram is not configured", chunk_count=0
            )

        chunks = self._chunk_message(message)
        first_message_id: str | None = None
        for index, chunk in enumerate(chunks, start=1):
            result = self._send_chunk_with_retry(chat_id=chat_id, message=chunk)
            if result.status != "sent":
                result.chunk_count = len(chunks)
                return result
            if first_message_id is None:
                first_message_id = result.provider_message_id
        return DeliveryResult(
            status="sent", provider_message_id=first_message_id, chunk_count=len(chunks)
        )

    def _send_chunk_with_retry(self, *, chat_id: str | int, message: str) -> DeliveryResult:
        endpoint = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": message,
            "disable_web_page_preview": True,
        }
        try:
            response = request_with_retry(
                request_callable=httpx.post,
                logger=logger,
                service_name="telegram",
                method="POST",
                url=endpoint,
                timeout=self.settings.request_timeout_seconds,
                retry_attempts=self.settings.telegram_retry_attempts,
                retry_base_seconds=self.settings.telegram_retry_base_seconds,
                headers=build_request_headers(self.settings),
                json=payload,
            )
        except Exception as exc:  # pragma: no cover - environment specific network failures
            return DeliveryResult(status="failed", error_message=str(exc), chunk_count=1)

        if response.status_code < 400:
            body = safe_response_json(response)
            message_id = body.get("result", {}).get("message_id")
            return DeliveryResult(
                status="sent",
                provider_message_id=str(message_id) if message_id else None,
                chunk_count=1,
            )

        error_message = self._extract_error_message(response)
        logger.error(
            "Telegram delivery failed with status %s: %s", response.status_code, error_message
        )
        return DeliveryResult(status="failed", error_message=error_message, chunk_count=1)

    def _chunk_message(self, message: str) -> list[str]:
        max_length = max(1, self.settings.telegram_message_chunk_size)
        if len(message) <= max_length:
            return [message]

        lines = message.splitlines(keepends=True)
        chunks: list[str] = []
        current = ""

        for line in lines:
            if len(line) > max_length:
                if current:
                    chunks.append(current.rstrip())
                    current = ""
                chunks.extend(self._hard_split(line, max_length))
                continue
            if len(current) + len(line) > max_length:
                if current:
                    chunks.append(current.rstrip())
                current = line
            else:
                current += line

        if current:
            chunks.append(current.rstrip())
        return chunks

    @staticmethod
    def _hard_split(text: str, max_length: int) -> list[str]:
        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining.rstrip())
                break
            split_at = remaining.rfind(" ", 0, max_length)
            if split_at <= 0:
                split_at = max_length
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        return chunks

    def _extract_error_message(self, response: httpx.Response) -> str:
        payload = safe_response_json(response)
        if payload.get("description"):
            return str(payload["description"])
        if response.text:
            return response.text[:500]
        return f"HTTP {response.status_code}"
