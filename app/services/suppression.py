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
        cutoff = utcnow() - timedelta(hours=self.settings.alert_cooldown_hours)
        previous = self.event_repository.latest_unsuppressed_for_dedupe_key(event.dedupe_key, cutoff)
        if previous is not None:
            event.is_suppressed = True
            event.suppressed_reason = "cooldown"
        return event
