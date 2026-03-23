from dataclasses import dataclass

import pytest

from app.core.config import Settings
from app.core.time import utcnow
from app.models.source import Source
from app.repositories.runs import RunRepository
from app.services.gemini import GeminiService
from app.services.monitor_runner import MonitorRunner, RunLockedError
from app.services.run_lock import SourceRunLockManager
from app.services.telegram import TelegramNotifier
from app.services.types import ParseResult, ParsedItem


@dataclass
class FakeAdapter:
    parser_key: str = "fake"
    responses: list[ParseResult] | None = None

    def __post_init__(self):
        self._calls = 0
        self.enrich_calls = 0

    def parse(self, source: Source) -> ParseResult:
        response = self.responses[self._calls]
        self._calls += 1
        return response

    def enrich_items(self, source: Source, items: list[ParsedItem]) -> list[ParsedItem]:
        self.enrich_calls += 1
        for parsed_item in items:
            parsed_item.attributes.setdefault("category", "Travel")
        return items


def make_source(session_factory) -> int:
    with session_factory() as session:
        now = utcnow()
        source = Source(
            name="Fake Source",
            slug="fake-source",
            parser_key="fake",
            base_url="https://example.com/",
            start_url="https://example.com/catalogue",
            schedule_enabled=True,
            schedule_interval_minutes=60,
            is_active=True,
            health_status="healthy",
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        return source.id


def item(index: int) -> ParsedItem:
    return ParsedItem(
        canonical_url=f"/catalogue/{index}",
        title=f"Item {index}",
        price_amount=10.0 + index,
        currency="GBP",
        availability_status="in_stock",
        rating="One",
    )


def build_runner(session_factory, adapter: FakeAdapter) -> MonitorRunner:
    settings = Settings()
    return MonitorRunner(
        session_factory=session_factory,
        settings=settings,
        parsers={"fake": adapter},
        lock_manager=SourceRunLockManager(),
        notifier=TelegramNotifier(settings),
        gemini_service=GeminiService(settings),
    )


def test_runner_creates_new_events_then_noops_on_repeat(session_factory) -> None:
    source_id = make_source(session_factory)
    adapter = FakeAdapter(
        responses=[
            ParseResult(items=[item(1)], pages_fetched=1),
            ParseResult(items=[item(1)], pages_fetched=1),
        ]
    )
    runner = build_runner(session_factory, adapter)

    first = runner.run_source(source_id)
    second = runner.run_source(source_id)

    assert first.status == "succeeded"
    assert first.events_count == 1
    assert second.events_count == 0


def test_runner_marks_removed_after_two_healthy_misses(session_factory) -> None:
    source_id = make_source(session_factory)
    initial_items = [item(index) for index in range(10)]
    follow_up_items = [item(index) for index in range(9)]
    adapter = FakeAdapter(
        responses=[
            ParseResult(items=initial_items, pages_fetched=1),
            ParseResult(items=follow_up_items, pages_fetched=1),
            ParseResult(items=follow_up_items, pages_fetched=1),
        ]
    )
    runner = build_runner(session_factory, adapter)

    runner.run_source(source_id)
    miss_one = runner.run_source(source_id)
    miss_two = runner.run_source(source_id)

    assert miss_one.removed_items_count == 0
    assert miss_two.removed_items_count == 1


def test_runner_reuses_cached_attributes_without_reenriching_existing_items(session_factory) -> None:
    source_id = make_source(session_factory)
    adapter = FakeAdapter(
        responses=[
            ParseResult(items=[item(1)], pages_fetched=1),
            ParseResult(items=[item(1)], pages_fetched=1),
        ]
    )
    runner = build_runner(session_factory, adapter)

    first = runner.run_source(source_id)
    second = runner.run_source(source_id)

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert adapter.enrich_calls == 1


def test_runner_can_queue_and_execute_run_lifecycle(session_factory) -> None:
    source_id = make_source(session_factory)
    adapter = FakeAdapter(responses=[ParseResult(items=[item(1)], pages_fetched=1)])
    runner = build_runner(session_factory, adapter)

    queued = runner.queue_run(source_id, trigger_type="manual")
    assert queued.status == "queued"

    with session_factory() as session:
        persisted = RunRepository(session).get(queued.id)
        assert persisted is not None
        assert persisted.status == "queued"

    finished = runner.run_queued_run(queued.id)

    assert finished.id == queued.id
    assert finished.status == "succeeded"
    assert finished.items_parsed == 1
    assert finished.events_count == 1


def test_runner_prevents_duplicate_queued_runs_for_same_source(session_factory) -> None:
    source_id = make_source(session_factory)
    adapter = FakeAdapter(responses=[ParseResult(items=[item(1)], pages_fetched=1)])
    runner = build_runner(session_factory, adapter)

    queued = runner.queue_run(source_id, trigger_type="manual")
    assert queued.status == "queued"

    with pytest.raises(RunLockedError):
        runner.queue_run(source_id, trigger_type="manual")
