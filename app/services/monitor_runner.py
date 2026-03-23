import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.time import utcnow
from app.models.ai_summary import AISummary
from app.models.event import DetectedEvent
from app.models.notification import NotificationLog
from app.models.run import MonitoringRun
from app.models.source import Source
from app.parsers.base import BaseSourceAdapter
from app.repositories.events import EventRepository
from app.repositories.items import ItemRepository
from app.repositories.monitor_profiles import MonitorProfileRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.runs import RunRepository
from app.repositories.sources import SourceRepository
from app.repositories.summaries import AISummaryRepository
from app.services.diff_engine import DiffEngine
from app.services.gemini import GeminiService
from app.services.monitor_evaluator import MonitorEvaluator
from app.services.normalization import NormalizationService
from app.services.priority_engine import PriorityEngine
from app.services.run_lock import SourceRunLockManager
from app.services.source_health import SourceHealthService
from app.services.suppression import SuppressionService
from app.services.telegram import TelegramNotifier
from app.services.telegram_notifier import MonitorTelegramNotifier
from app.services.types import EventDraft

logger = logging.getLogger(__name__)


class RunLockedError(RuntimeError):
    pass


class MonitorRunner:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        settings: Settings,
        parsers: dict[str, BaseSourceAdapter],
        lock_manager: SourceRunLockManager,
        notifier: TelegramNotifier,
        gemini_service: GeminiService,
        monitor_notifier: MonitorTelegramNotifier | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.parsers = parsers
        self.lock_manager = lock_manager
        self.notifier = notifier
        self.gemini_service = gemini_service
        self.normalizer = NormalizationService()
        self.diff_engine = DiffEngine(settings)
        self.priority_engine = PriorityEngine()
        self.health_service = SourceHealthService(settings)
        self.monitor_evaluator = MonitorEvaluator()
        self.monitor_notifier = monitor_notifier

    def queue_run(self, source_id: int, trigger_type: str = "manual") -> MonitoringRun:
        with self.session_factory() as session:
            source_repo = SourceRepository(session)
            run_repo = RunRepository(session)
            source = source_repo.get(source_id)
            if source is None:
                raise ValueError(f"Source {source_id} not found")
            active_run = run_repo.get_in_progress_by_source(source_id)
            if active_run is not None:
                raise RunLockedError(
                    f"Source {source_id} already has an in-progress run #{active_run.id}"
                )
            queued_at = utcnow()
            run = run_repo.create_run(
                source_id=source.id,
                trigger_type=trigger_type,
                started_at=queued_at,
                status="queued",
            )
            session.refresh(run)
            return run

    def run_source(self, source_id: int, trigger_type: str = "manual") -> MonitoringRun:
        with self.lock_manager.held(source_id) as acquired:
            if not acquired:
                raise RunLockedError(f"Source {source_id} is already running")

            with self.session_factory() as session:
                source_repo = SourceRepository(session)
                run_repo = RunRepository(session)
                source = source_repo.get(source_id)
                if source is None:
                    raise ValueError(f"Source {source_id} not found")

                previous_health = source.health_status
                run = run_repo.create_run(
                    source_id=source.id,
                    trigger_type=trigger_type,
                    started_at=utcnow(),
                    status="running",
                )
                started_at = self._mark_run_started(session=session, source=source, run=run)

                try:
                    return self._execute_run(session=session, source=source, run=run)
                except Exception as exc:
                    return self._handle_failed_run(
                        session=session,
                        source=source,
                        run=run,
                        previous_health=previous_health,
                        started_at=started_at,
                        exc=exc,
                    )

    def run_queued_run(self, run_id: int) -> MonitoringRun:
        with self.session_factory() as session:
            run_repo = RunRepository(session)
            source_repo = SourceRepository(session)
            run = run_repo.get(run_id)
            if run is None:
                raise ValueError(f"Run {run_id} not found")
            source = source_repo.get(run.source_id)
            if source is None:
                raise ValueError(f"Source {run.source_id} not found")
            if run.status not in {"queued", "running"}:
                return run

        with self.lock_manager.held(source.id) as acquired:
            if not acquired:
                with self.session_factory() as session:
                    run = RunRepository(session).get(run_id)
                    source = (
                        SourceRepository(session).get(run.source_id) if run is not None else None
                    )
                    if run is None or source is None:
                        raise RunLockedError(f"Run {run_id} is no longer available")
                    if run.status == "queued":
                        previous_health = source.health_status
                        return self._handle_failed_run(
                            session=session,
                            source=source,
                            run=run,
                            previous_health=previous_health,
                            started_at=run.started_at,
                            exc=RunLockedError(f"Source {source.id} is already running"),
                        )
                    raise RunLockedError(f"Source {source.id} is already running")

            with self.session_factory() as session:
                run_repo = RunRepository(session)
                source_repo = SourceRepository(session)
                run = run_repo.get(run_id)
                if run is None:
                    raise ValueError(f"Run {run_id} not found")
                source = source_repo.get(run.source_id)
                if source is None:
                    raise ValueError(f"Source {run.source_id} not found")

                previous_health = source.health_status
                started_at = self._mark_run_started(session=session, source=source, run=run)
                try:
                    return self._execute_run(session=session, source=source, run=run)
                except Exception as exc:
                    return self._handle_failed_run(
                        session=session,
                        source=source,
                        run=run,
                        previous_health=previous_health,
                        started_at=started_at,
                        exc=exc,
                    )

    def _execute_run(
        self, *, session: Session, source: Source, run: MonitoringRun
    ) -> MonitoringRun:
        run_repo = RunRepository(session)
        item_repo = ItemRepository(session)
        event_repo = EventRepository(session)
        summary_repo = AISummaryRepository(session)
        notification_repo = NotificationRepository(session)
        suppression_service = SuppressionService(self.settings, event_repo)

        adapter = self.parsers[source.parser_key]
        parse_result = adapter.parse(source)
        item_count = len(parse_result.items)

        recent_counts = run_repo.recent_healthy_item_counts(
            source.id, self.settings.health_baseline_run_window
        )
        health = self.health_service.evaluate(
            item_count=item_count,
            warnings=parse_result.warnings,
            recent_healthy_counts=recent_counts,
        )

        if health.status == "failing":
            raise RuntimeError("Parser returned no usable items")

        all_items = item_repo.get_by_source(source.id)
        raw_items = list(parse_result.items)
        items_to_enrich = self._hydrate_cached_attributes(
            source=source, items=raw_items, existing_items=all_items
        )
        if items_to_enrich:
            adapter.enrich_items(source, items_to_enrich)
        normalized_items = [self.normalizer.normalize(source, item) for item in raw_items]
        active_current_items = {key: item for key, item in all_items.items() if item.is_active}
        seen_keys: set[str] = set()
        draft_items: list[tuple[EventDraft, Source | Any]] = []
        items_for_snapshots = []
        persisted_items_by_id = {}
        now = utcnow()

        for normalized in normalized_items:
            existing = all_items.get(normalized.source_item_key)
            if existing is None:
                item = item_repo.create_from_normalized(source.id, normalized, now, flush=False)
                draft = self.diff_engine.new_item_event(source.id, normalized, item_id=None)
            else:
                was_active = existing.is_active
                draft = self.diff_engine.compare(existing, normalized) if was_active else None
                item = item_repo.update_from_normalized(existing, normalized, now, flush=False)
                if not was_active:
                    draft = self.diff_engine.new_item_event(source.id, normalized, item_id=None)

            seen_keys.add(normalized.source_item_key)
            items_for_snapshots.append(item)
            if draft is not None:
                draft_items.append((self.priority_engine.assign(draft), item))

        if health.status == "healthy":
            for key, item in active_current_items.items():
                if key in seen_keys:
                    continue
                item_repo.increment_missing(item, now, flush=False)
                if item.missing_run_count >= self.settings.removal_miss_threshold:
                    item_repo.mark_removed(item, now, flush=False)
                    draft = self.diff_engine.removed_item_event(item)
                    draft_items.append((self.priority_engine.assign(draft), item))

        drafts = [draft for draft, _ in draft_items]
        drafts = suppression_service.apply_batch(drafts)
        session.flush()

        for item in items_for_snapshots:
            persisted_items_by_id[item.id] = item

        item_repo.create_snapshots(items_for_snapshots, run.id, now)

        event_models = [
            self._build_event_model(
                run=run,
                source=source,
                draft=self._assign_item_id(draft=draft, item=item),
                created_at=now,
            )
            for draft, item in draft_items
        ]
        event_repo.save_all(event_models)

        finished_at = utcnow()
        run.finished_at = finished_at
        run.duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)
        run.pages_fetched = parse_result.pages_fetched
        run.items_parsed = item_count
        run.new_items_count = len(
            [event for event in event_models if event.event_type == "new_item"]
        )
        run.changed_items_count = len(
            [
                event
                for event in event_models
                if event.event_type not in {"new_item", "removed_item"}
            ]
        )
        run.removed_items_count = len(
            [event for event in event_models if event.event_type == "removed_item"]
        )
        run.events_count = len(event_models)
        run.parse_completeness_ratio = round(health.parse_completeness_ratio, 2)
        run.health_evaluation = health.status
        run.status = "degraded" if health.status == "degraded" else "succeeded"
        run.error_message = None

        source.health_status = health.status
        source.last_run_finished_at = finished_at
        source.last_successful_run_at = finished_at
        source.consecutive_failures = 0
        source.last_error_message = None
        source.updated_at = finished_at

        summary_result = self.gemini_service.summarize_run(
            source,
            run,
            self._prioritize_unsuppressed_events(event_models),
        )
        summary = AISummary(
            run_id=run.id,
            source_id=source.id,
            model_name=self.settings.gemini_model,
            prompt_version=self.gemini_service.PROMPT_VERSION,
            summary_text=summary_result.summary_text,
            highlights_json=summary_result.highlights,
            status=summary_result.status,
            response_json=summary_result.raw_response,
            created_at=finished_at,
        )
        summary_repo.save(summary)

        session.add_all([source, run])
        session.commit()

        alert_count = 0
        prioritized_events = self._prioritize_unsuppressed_events(event_models)
        active_profiles = list(MonitorProfileRepository(session).list_active_by_source(source.id))
        if active_profiles and self.monitor_notifier is not None:
            evaluated_matches = self.monitor_evaluator.evaluate(
                source=source,
                run=run,
                profiles=active_profiles,
                events=event_models,
                items_by_id=persisted_items_by_id,
            )
            self.monitor_notifier.persist_matches(evaluated_matches)
            alert_count += self.monitor_notifier.deliver(
                source=source,
                run=run,
                summary=summary,
                matches=evaluated_matches,
            )
        else:
            notification_logs: list[NotificationLog] = []
            for event in prioritized_events:
                if event.severity != "high":
                    continue
                item = persisted_items_by_id.get(event.item_id) if event.item_id else None
                result = self.notifier.send_event_alert(source, run, event, item)
                notification_logs.append(
                    NotificationLog(
                        run_id=run.id,
                        event_id=event.id,
                        source_id=source.id,
                        channel="telegram",
                        notification_type="immediate_alert",
                        destination=self.settings.telegram_chat_id,
                        status=result.status,
                        provider_message_id=result.provider_message_id,
                        payload_preview=event.summary_text,
                        sent_at=utcnow(),
                        error_message=result.error_message,
                    )
                )
                if result.status == "sent":
                    alert_count += 1

            if prioritized_events:
                result = self.notifier.send_run_digest(
                    source=source,
                    run=run,
                    events=prioritized_events,
                    summary_text=summary.summary_text,
                )
                notification_logs.append(
                    NotificationLog(
                        run_id=run.id,
                        event_id=None,
                        source_id=source.id,
                        channel="telegram",
                        notification_type="digest",
                        destination=self.settings.telegram_chat_id,
                        status=result.status,
                        provider_message_id=result.provider_message_id,
                        payload_preview=summary.summary_text,
                        sent_at=utcnow(),
                        error_message=result.error_message,
                    )
                )
                if result.status == "sent":
                    alert_count += 1

            notification_repo.save_all(notification_logs)

        run.alerts_sent_count = alert_count
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    def _mark_run_started(
        self, *, session: Session, source: Source, run: MonitoringRun
    ) -> datetime:
        started_at = utcnow()
        run.status = "running"
        run.started_at = started_at
        source.last_run_started_at = started_at
        source.updated_at = started_at
        session.add_all([source, run])
        session.commit()
        session.refresh(run)
        return started_at

    def _handle_failed_run(
        self,
        *,
        session: Session,
        source: Source,
        run: MonitoringRun,
        previous_health: str,
        started_at: datetime,
        exc: Exception,
    ) -> MonitoringRun:
        logger.exception("Monitoring run failed for source %s", source.slug)
        session.rollback()
        finished_at = utcnow()
        source.health_status = "failing"
        source.last_run_finished_at = finished_at
        source.last_failed_run_at = finished_at
        source.consecutive_failures += 1
        source.last_error_message = str(exc)
        source.updated_at = finished_at

        run.status = "failed"
        run.finished_at = finished_at
        run.duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        run.health_evaluation = "failing"
        run.error_message = str(exc)

        session.add_all([source, run])
        session.commit()
        session.refresh(run)

        if previous_health != "failing":
            self._log_failure_transition(session, source, run, str(exc))
        return run

    def _log_failure_transition(
        self, session: Session, source: Source, run: MonitoringRun, error_message: str
    ) -> None:
        notification_repo = NotificationRepository(session)
        result = self.notifier.send_failure_alert(source, error_message)
        notification_repo.save(
            NotificationLog(
                run_id=run.id,
                event_id=None,
                source_id=source.id,
                channel="telegram",
                notification_type="health_alert",
                destination=self.settings.telegram_chat_id,
                status=result.status,
                provider_message_id=result.provider_message_id,
                payload_preview=error_message,
                sent_at=utcnow(),
                error_message=result.error_message,
            )
        )
        session.commit()

    @staticmethod
    def _build_event_model(
        *, run: MonitoringRun, source: Source, draft: EventDraft, created_at: datetime
    ) -> DetectedEvent:
        return DetectedEvent(
            run_id=run.id,
            source_id=source.id,
            item_id=draft.item_id,
            event_type=draft.event_type,
            severity=draft.severity,
            dedupe_key=draft.dedupe_key,
            old_value_json=draft.old_value,
            new_value_json=draft.new_value,
            changed_fields_json=draft.changed_fields,
            summary_text=draft.summary_text,
            is_suppressed=draft.is_suppressed,
            suppressed_reason=draft.suppressed_reason,
            created_at=created_at,
        )

    @staticmethod
    def _assign_item_id(draft: EventDraft, item: Any) -> EventDraft:
        if draft.item_id is None and item is not None:
            draft.item_id = item.id
        return draft

    @staticmethod
    def _prioritize_unsuppressed_events(events: list[DetectedEvent]) -> list[DetectedEvent]:
        severity_order = {"high": 0, "medium": 1, "low": 2}
        unsuppressed = [event for event in events if not event.is_suppressed]
        return sorted(
            unsuppressed, key=lambda event: (severity_order.get(event.severity, 9), event.id or 0)
        )

    def _hydrate_cached_attributes(
        self,
        *,
        source: Source,
        items: list,
        existing_items: dict[str, Any],
    ) -> list:
        items_to_enrich = []
        for item in items:
            source_item_key = self.normalizer.build_source_item_key(source, item.canonical_url)
            existing = existing_items.get(source_item_key)
            existing_attributes = (
                existing.attributes_json
                if existing is not None and existing.attributes_json
                else {}
            )
            for key, value in existing_attributes.items():
                item.attributes.setdefault(key, value)
            if not item.attributes.get("category"):
                items_to_enrich.append(item)
        return items_to_enrich


def build_runner_dependencies(settings: Settings) -> dict[str, Any]:
    from app.core.db import SessionLocal
    from app.parsers.books_toscrape import BooksToScrapeAdapter
    from app.services.run_lock import SourceRunLockManager
    from app.services.telegram_notifier import MonitorTelegramNotifier

    notifier = TelegramNotifier(settings)
    gemini_service = GeminiService(settings)
    lock_manager = SourceRunLockManager()
    monitor_notifier = MonitorTelegramNotifier(
        session_factory=SessionLocal,
        notifier=notifier,
        evaluator=MonitorEvaluator(),
    )
    parsers = {
        BooksToScrapeAdapter.parser_key: BooksToScrapeAdapter(settings),
    }
    return {
        "session_factory": SessionLocal,
        "settings": settings,
        "parsers": parsers,
        "lock_manager": lock_manager,
        "notifier": notifier,
        "gemini_service": gemini_service,
        "monitor_notifier": monitor_notifier,
    }
