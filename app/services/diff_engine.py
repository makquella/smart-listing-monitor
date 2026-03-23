from app.core.config import Settings
from app.models.item import Item
from app.services.types import EventDraft, NormalizedItem


class DiffEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def compare(self, existing: Item, normalized: NormalizedItem) -> EventDraft | None:
        if existing.comparison_hash == normalized.comparison_hash:
            return None

        old_value = {
            "title": existing.title,
            "price_amount": existing.price_amount,
            "currency": existing.currency,
            "availability_status": existing.availability_status,
            "rating": existing.rating,
        }
        new_value = {
            "title": normalized.title,
            "price_amount": normalized.price_amount,
            "currency": normalized.currency,
            "availability_status": normalized.availability_status,
            "rating": normalized.rating,
        }

        if existing.availability_status != normalized.availability_status:
            changed_fields = ["availability_status"]
            if existing.price_amount != normalized.price_amount:
                changed_fields.append("price_amount")
                old_value["price_delta"] = 0.0
                new_value.update(self._price_delta(existing.price_amount, normalized.price_amount))
            summary = self._build_availability_summary(existing, normalized)
            return EventDraft(
                source_item_key=normalized.source_item_key,
                item_id=existing.id,
                event_type="availability_change",
                severity="medium",
                dedupe_key=f"{existing.source_id}:{normalized.source_item_key}:availability_change",
                old_value=old_value,
                new_value=new_value,
                changed_fields=changed_fields,
                summary_text=summary,
            )

        if self._is_significant_price_change(existing.price_amount, normalized.price_amount):
            deltas = self._price_delta(existing.price_amount, normalized.price_amount)
            new_value.update(deltas)
            old_value.update(deltas)
            direction = "down" if deltas["price_delta"] < 0 else "up"
            summary = (
                f'Price changed for "{normalized.title}" '
                f"from {self._fmt_price(existing.price_amount, existing.currency)} "
                f"to {self._fmt_price(normalized.price_amount, normalized.currency)} "
                f"({direction} {abs(deltas['price_delta_percent']):.1f}%)"
            )
            return EventDraft(
                source_item_key=normalized.source_item_key,
                item_id=existing.id,
                event_type="price_change",
                severity="low",
                dedupe_key=f"{existing.source_id}:{normalized.source_item_key}:price_change",
                old_value=old_value,
                new_value=new_value,
                changed_fields=["price_amount"],
                summary_text=summary,
            )

        changed_fields: list[str] = []
        if existing.title != normalized.title:
            changed_fields.append("title")
        if existing.rating != normalized.rating:
            changed_fields.append("rating")

        if not changed_fields:
            return None

        summary = f'Attributes changed for "{normalized.title}": {", ".join(changed_fields)}'
        return EventDraft(
            source_item_key=normalized.source_item_key,
            item_id=existing.id,
            event_type="attribute_change",
            severity="low",
            dedupe_key=f"{existing.source_id}:{normalized.source_item_key}:attribute_change",
            old_value=old_value,
            new_value=new_value,
            changed_fields=changed_fields,
            summary_text=summary,
        )

    def new_item_event(
        self, source_id: int, normalized: NormalizedItem, item_id: int | None = None
    ) -> EventDraft:
        return EventDraft(
            source_item_key=normalized.source_item_key,
            item_id=item_id,
            event_type="new_item",
            severity="medium",
            dedupe_key=f"{source_id}:{normalized.source_item_key}:new_item",
            old_value=None,
            new_value={
                "title": normalized.title,
                "price_amount": normalized.price_amount,
                "currency": normalized.currency,
                "availability_status": normalized.availability_status,
                "rating": normalized.rating,
            },
            changed_fields=["title", "price_amount", "availability_status", "rating"],
            summary_text=(
                f'New item detected: "{normalized.title}" '
                f"at {self._fmt_price(normalized.price_amount, normalized.currency)}"
            ),
        )

    def removed_item_event(self, item: Item) -> EventDraft:
        return EventDraft(
            source_item_key=item.source_item_key,
            item_id=item.id,
            event_type="removed_item",
            severity="medium",
            dedupe_key=f"{item.source_id}:{item.source_item_key}:removed_item",
            old_value={
                "title": item.title,
                "price_amount": item.price_amount,
                "currency": item.currency,
                "availability_status": item.availability_status,
                "rating": item.rating,
            },
            new_value=None,
            changed_fields=["is_active"],
            summary_text=f'Item removed after {item.missing_run_count} consecutive misses: "{item.title}"',
        )

    def _is_significant_price_change(self, previous: float | None, current: float | None) -> bool:
        if previous is None or current is None or previous == current:
            return False
        delta = abs(current - previous)
        percent = abs((delta / previous) * 100) if previous else 0.0
        return (
            delta >= self.settings.min_absolute_price_delta
            or percent >= self.settings.min_percent_price_delta
        )

    def _price_delta(self, previous: float | None, current: float | None) -> dict:
        if previous is None or current is None:
            return {"price_delta": 0.0, "price_delta_percent": 0.0}
        delta = round(current - previous, 2)
        percent = round((delta / previous) * 100, 2) if previous else 0.0
        return {"price_delta": delta, "price_delta_percent": percent}

    def _build_availability_summary(self, existing: Item, normalized: NormalizedItem) -> str:
        base = f'Availability changed for "{normalized.title}": {existing.availability_status} -> {normalized.availability_status}'
        if self._is_significant_price_change(existing.price_amount, normalized.price_amount):
            deltas = self._price_delta(existing.price_amount, normalized.price_amount)
            return f"{base}, price moved {deltas['price_delta_percent']:.1f}%"
        return base

    @staticmethod
    def _fmt_price(price: float | None, currency: str | None) -> str:
        if price is None:
            return "n/a"
        prefix = f"{currency} " if currency else ""
        return f"{prefix}{price:.2f}"
