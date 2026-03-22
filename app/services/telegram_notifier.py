from collections import defaultdict

from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utcnow
from app.models.ai_summary import AISummary
from app.models.monitor_match import MonitorMatch
from app.models.notification_delivery import NotificationDelivery
from app.models.run import MonitoringRun
from app.models.source import Source
from app.models.telegram_chat import TelegramChat
from app.repositories.deliveries import NotificationDeliveryRepository
from app.repositories.monitor_matches import MonitorMatchRepository
from app.repositories.monitor_profiles import MonitorProfileRepository
from app.services.digest_builder import DigestBuilder
from app.services.monitor_evaluator import EvaluatedMonitorMatch, MonitorEvaluator
from app.services.telegram import TelegramNotifier


class MonitorTelegramNotifier:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        notifier: TelegramNotifier,
        evaluator: MonitorEvaluator,
    ) -> None:
        self.session_factory = session_factory
        self.notifier = notifier
        self.evaluator = evaluator
        self.digest_builder = DigestBuilder()

    def persist_matches(self, matches: list[EvaluatedMonitorMatch]) -> list[MonitorMatch]:
        if not matches:
            return []
        with self.session_factory() as session:
            repo = MonitorMatchRepository(session)
            created = [
                repo.save(
                    MonitorMatch(
                        monitor_profile_id=match.draft.monitor_profile_id,
                        detected_event_id=match.draft.detected_event_id,
                        monitoring_run_id=match.draft.monitoring_run_id,
                        matched=match.draft.matched,
                        match_reason=match.draft.match_reason,
                        priority=match.draft.priority,
                        created_at=utcnow(),
                    )
                )
                for match in matches
            ]
            session.commit()
            return created

    def deliver(
        self,
        *,
        source: Source,
        run: MonitoringRun,
        summary: AISummary,
        matches: list[EvaluatedMonitorMatch],
    ) -> int:
        if not matches:
            return 0

        alert_count = 0
        with self.session_factory() as session:
            delivery_repo = NotificationDeliveryRepository(session)
            grouped_by_profile: dict[int, list[EvaluatedMonitorMatch]] = defaultdict(list)
            for match in matches:
                grouped_by_profile[match.profile.id].append(match)

            for profile_matches in grouped_by_profile.values():
                profile_stub = profile_matches[0].profile
                profile = MonitorProfileRepository(session).get(profile_stub.id)
                if profile is None:
                    continue
                chat = session.get(TelegramChat, profile.telegram_chat_id)
                if chat is None:
                    continue
                allowed_matches = [
                    match
                    for match in profile_matches
                    if self.evaluator.should_deliver(profile, match.draft.priority)
                ]
                if not allowed_matches:
                    continue

                if profile.instant_alerts_enabled:
                    for match in allowed_matches:
                        status = "suppressed" if match.event.is_suppressed else "queued"
                        preview = self._format_instant_alert(profile.name, match)
                        if not match.event.is_suppressed:
                            result = self.notifier.send_message(chat.telegram_chat_id, preview)
                            status = result.status
                            telegram_message_id = result.provider_message_id
                            error_text = result.error_message
                            if result.status == "sent":
                                alert_count += 1
                        else:
                            telegram_message_id = None
                            error_text = match.event.suppressed_reason or "Suppressed by platform rules"

                        delivery_repo.save(
                            NotificationDelivery(
                                monitor_profile_id=profile.id,
                                telegram_chat_id=chat.id,
                                detected_event_id=match.event.id,
                                monitoring_run_id=run.id,
                                delivery_type="instant",
                                status=status,
                                message_preview=preview,
                                telegram_message_id=telegram_message_id,
                                error_text=error_text,
                                created_at=utcnow(),
                                sent_at=utcnow() if status == "sent" else None,
                            )
                        )

                if profile.digest_enabled:
                    digest_matches = [match for match in allowed_matches if not match.event.is_suppressed]
                    if not digest_matches:
                        continue
                    digest_preview = self.digest_builder.build_run_digest(
                        profile=profile,
                        source=source,
                        run=run,
                        matches=digest_matches,
                        summary_text=summary.summary_text,
                    )
                    result = self.notifier.send_message(chat.telegram_chat_id, digest_preview)
                    delivery_repo.save(
                        NotificationDelivery(
                            monitor_profile_id=profile.id,
                            telegram_chat_id=chat.id,
                            detected_event_id=None,
                            monitoring_run_id=run.id,
                            delivery_type="digest",
                            status=result.status,
                            message_preview=digest_preview,
                            telegram_message_id=result.provider_message_id,
                            error_text=result.error_message,
                            created_at=utcnow(),
                            sent_at=utcnow() if result.status == "sent" else None,
                        )
                    )
                    if result.status == "sent":
                        alert_count += 1

            session.commit()
        return alert_count

    @staticmethod
    def _format_instant_alert(monitor_name: str, match: EvaluatedMonitorMatch) -> str:
        item = match.item
        lines = [
            f"[{match.draft.priority.upper()}] {monitor_name}",
            match.event.summary_text,
            f"Why matched: {match.draft.match_reason}",
        ]
        if item is not None and item.price_amount is not None:
            lines.append(f"Price: {item.currency} {item.price_amount:.2f}")
        if item is not None:
            category = item.attributes_json.get("category")
            if category:
                lines.append(f"Category: {category}")
            lines.append(f"Open item: {item.canonical_url}")
        return "\n".join(lines)
