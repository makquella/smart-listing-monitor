from app.core.config import Settings
from app.services.suppression import SuppressionService
from app.services.types import EventDraft


class FakeEventRepository:
    def __init__(self, suppressed_keys: set[str]):
        self.suppressed_keys = suppressed_keys
        self.calls: list[tuple[tuple[str, ...], object]] = []

    def latest_unsuppressed_for_dedupe_keys(self, dedupe_keys, since):
        self.calls.append((tuple(dedupe_keys), since))
        return {key: object() for key in dedupe_keys if key in self.suppressed_keys}


def make_draft(dedupe_key: str) -> EventDraft:
    return EventDraft(
        source_item_key=f"key-{dedupe_key}",
        item_id=None,
        event_type="price_change",
        severity="medium",
        dedupe_key=dedupe_key,
        old_value={"price": 10},
        new_value={"price": 8},
        changed_fields=["price_amount"],
        summary_text=f"Price changed for {dedupe_key}",
    )


def test_suppression_service_prefetches_dedupe_keys_in_one_call() -> None:
    repository = FakeEventRepository({"dup-a"})
    service = SuppressionService(Settings(ALERT_COOLDOWN_HOURS=12), repository)
    drafts = [make_draft("dup-a"), make_draft("dup-b"), make_draft("dup-a")]

    result = service.apply_batch(drafts)

    assert len(repository.calls) == 1
    assert repository.calls[0][0] == ("dup-a", "dup-b")
    assert result[0].is_suppressed is True
    assert result[0].suppressed_reason == "cooldown"
    assert result[1].is_suppressed is False
    assert result[2].is_suppressed is True


def test_suppression_service_apply_uses_batch_logic_for_single_event() -> None:
    repository = FakeEventRepository({"dup-a"})
    service = SuppressionService(Settings(ALERT_COOLDOWN_HOURS=12), repository)

    result = service.apply(make_draft("dup-a"))

    assert len(repository.calls) == 1
    assert repository.calls[0][0] == ("dup-a",)
    assert result.is_suppressed is True
    assert result.suppressed_reason == "cooldown"
