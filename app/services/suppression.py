from datetime import timedelta

from app.core.config import Settings
from app.core.time import utcnow
from app.repositories.events import EventRepository
from app.services.types import EventDraft


class SuppressionService:
    def __init__(self, settings: Settings, event_repository: EventRepository):
        self.settings = settings
        self.event_repository = event_repository

    def apply(self, event: EventDraft) -> EventDraft:
        return self.apply_batch([event])[0]

    def apply_batch(self, events: list[EventDraft]) -> list[EventDraft]:
        if not events:
            return events

        cutoff = utcnow() - timedelta(hours=self.settings.alert_cooldown_hours)
        dedupe_keys = sorted({event.dedupe_key for event in events if event.dedupe_key})
        latest_by_key = self.event_repository.latest_unsuppressed_for_dedupe_keys(
            dedupe_keys, cutoff
        )

        for event in events:
            if event.dedupe_key in latest_by_key:
                event.is_suppressed = True
                event.suppressed_reason = "cooldown"

        return events
