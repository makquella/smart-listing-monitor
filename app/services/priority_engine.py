from app.services.types import EventDraft


class PriorityEngine:
    def assign(self, event: EventDraft) -> EventDraft:
        event.severity = self._severity_for(event)
        return event

    def _severity_for(self, event: EventDraft) -> str:
        if event.event_type == "availability_change":
            new_status = (event.new_value or {}).get("availability_status")
            if new_status == "in_stock":
                return "high"
            return "medium"

        if event.event_type == "price_change":
            price_delta = abs((event.new_value or {}).get("price_delta", 0))
            percent_delta = abs((event.new_value or {}).get("price_delta_percent", 0))
            if percent_delta >= 15 or price_delta >= 15:
                return "high"
            if percent_delta >= 5 or price_delta >= 5:
                return "medium"
            return "low"

        if event.event_type == "new_item":
            return "medium"

        if event.event_type == "removed_item":
            return "medium"

        if event.event_type == "attribute_change":
            if "title" in event.changed_fields:
                return "medium"
            return "low"

        return "low"
