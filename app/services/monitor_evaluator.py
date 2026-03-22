from dataclasses import dataclass

from app.models.event import DetectedEvent
from app.models.item import Item
from app.models.monitor_profile import MonitorProfile
from app.models.run import MonitoringRun
from app.models.source import Source
from app.services.types import MonitorMatchDraft


@dataclass(slots=True)
class EvaluatedMonitorMatch:
    draft: MonitorMatchDraft
    profile: MonitorProfile
    event: DetectedEvent
    item: Item | None


class MonitorEvaluator:
    PRIORITY_RANK = {"low": 1, "medium": 2, "high": 3}

    def evaluate(
        self,
        *,
        source: Source,
        run: MonitoringRun,
        profiles: list[MonitorProfile],
        events: list[DetectedEvent],
        items_by_id: dict[int, Item],
    ) -> list[EvaluatedMonitorMatch]:
        matches: list[EvaluatedMonitorMatch] = []
        for event in events:
            item = items_by_id.get(event.item_id) if event.item_id else None
            for profile in profiles:
                evaluated = self._evaluate_single(
                    source=source,
                    run=run,
                    profile=profile,
                    event=event,
                    item=item,
                )
                if evaluated is not None:
                    matches.append(evaluated)
        return matches

    def _evaluate_single(
        self,
        *,
        source: Source,
        run: MonitoringRun,
        profile: MonitorProfile,
        event: DetectedEvent,
        item: Item | None,
    ) -> EvaluatedMonitorMatch | None:
        if profile.source_id != source.id or not profile.is_active:
            return None

        searchable_parts = [
            event.summary_text,
            item.title if item else None,
            item.attributes_json.get("category") if item else None,
        ]
        searchable_text = " ".join(part for part in searchable_parts if part).lower()
        category = (item.attributes_json.get("category") if item else None) or ""
        price_amount = self._resolve_price(item, event)
        reasons: list[str] = []

        if profile.category:
            if category.lower() != profile.category.lower():
                return None
            reasons.append(f"category={category}")

        if profile.min_price is not None and (price_amount is None or price_amount < profile.min_price):
            return None
        if profile.max_price is not None and (price_amount is None or price_amount > profile.max_price):
            return None
        if profile.min_price is not None or profile.max_price is not None:
            reasons.append(f"price={price_amount:.2f}" if price_amount is not None else "price=n/a")

        include_matches = [keyword for keyword in profile.include_keywords_json if keyword in searchable_text]
        if profile.include_keywords_json and not include_matches:
            return None
        if include_matches:
            reasons.append(f"include={', '.join(include_matches)}")

        exclude_matches = [keyword for keyword in profile.exclude_keywords_json if keyword in searchable_text]
        if exclude_matches:
            return None

        priority = self._derive_priority(
            event=event,
            price_amount=price_amount,
            profile=profile,
            include_matches=include_matches,
        )
        reasons.append(f"event={event.event_type}")
        if event.is_suppressed:
            reasons.append("platform_suppressed")

        return EvaluatedMonitorMatch(
            draft=MonitorMatchDraft(
                monitor_profile_id=profile.id,
                detected_event_id=event.id,
                monitoring_run_id=run.id,
                matched=True,
                match_reason="; ".join(reasons),
                priority=priority,
            ),
            profile=profile,
            event=event,
            item=item,
        )

    def should_deliver(self, profile: MonitorProfile, match_priority: str) -> bool:
        allowed = {
            "high_only": {"high"},
            "high_medium": {"high", "medium"},
            "all": {"high", "medium", "low"},
        }
        return match_priority in allowed.get(profile.priority_mode, {"high", "medium"})

    def _derive_priority(
        self,
        *,
        event: DetectedEvent,
        price_amount: float | None,
        profile: MonitorProfile,
        include_matches: list[str],
    ) -> str:
        score = self.PRIORITY_RANK.get(event.severity, 1)
        if include_matches:
            score += 1
        if profile.max_price is not None and price_amount is not None and price_amount <= profile.max_price:
            score += 1
        if event.event_type == "availability_change" and (event.new_value_json or {}).get("availability_status") == "in_stock":
            score += 1
        if event.event_type == "new_item" and include_matches:
            score += 1
        score = max(1, min(score, 3))
        return {1: "low", 2: "medium", 3: "high"}[score]

    @staticmethod
    def _resolve_price(item: Item | None, event: DetectedEvent) -> float | None:
        if item is not None and item.price_amount is not None:
            return item.price_amount
        if event.new_value_json and event.new_value_json.get("price_amount") is not None:
            return float(event.new_value_json["price_amount"])
        if event.old_value_json and event.old_value_json.get("price_amount") is not None:
            return float(event.old_value_json["price_amount"])
        return None
