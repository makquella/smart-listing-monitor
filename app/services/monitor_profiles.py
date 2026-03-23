from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utcnow
from app.models.monitor_profile import MonitorProfile
from app.repositories.monitor_profiles import MonitorProfileRepository
from app.repositories.sources import SourceRepository
from app.repositories.telegram_registry import TelegramChatRepository
from app.services.telegram_registry import TelegramRegistryService
from app.services.types import MonitorProfileCreate


class MonitorProfileService:
    VALID_PRIORITY_MODES = {"high_only", "high_medium", "all"}

    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory
        self.registry = TelegramRegistryService(session_factory)

    @staticmethod
    def normalize_keywords(raw_keywords: list[str] | str | None) -> list[str]:
        if raw_keywords is None:
            return []
        if isinstance(raw_keywords, str):
            values = raw_keywords.split(",")
        else:
            values = raw_keywords
        return [value.strip().lower() for value in values if value and value.strip()]

    def create(self, payload: MonitorProfileCreate) -> MonitorProfile:
        if payload.priority_mode not in self.VALID_PRIORITY_MODES:
            raise ValueError(f"Unsupported priority mode: {payload.priority_mode}")
        if (
            payload.min_price is not None
            and payload.max_price is not None
            and payload.min_price > payload.max_price
        ):
            raise ValueError("Minimum price cannot be greater than maximum price")

        identity = self.registry.ensure_identity(
            telegram_user_id=payload.telegram_user_external_id,
            telegram_chat_id=payload.telegram_chat_external_id,
            chat_type=payload.chat_type,
            username=payload.username,
            first_name=payload.first_name,
            last_name=payload.last_name,
            chat_title=payload.chat_title,
        )
        with self.session_factory() as session:
            source = SourceRepository(session).get(payload.source_id)
            if source is None:
                raise ValueError(f"Source {payload.source_id} not found")
            now = utcnow()
            profile = MonitorProfile(
                telegram_user_id=identity.user.id,
                telegram_chat_id=identity.chat.id,
                source_id=payload.source_id,
                name=payload.name.strip(),
                is_active=True,
                category=payload.category.strip() if payload.category else None,
                min_price=payload.min_price,
                max_price=payload.max_price,
                include_keywords_json=self.normalize_keywords(payload.include_keywords),
                exclude_keywords_json=self.normalize_keywords(payload.exclude_keywords),
                instant_alerts_enabled=payload.instant_alerts_enabled,
                digest_enabled=payload.digest_enabled,
                priority_mode=payload.priority_mode,
                created_at=now,
                updated_at=now,
            )
            repo = MonitorProfileRepository(session)
            repo.save(profile)
            session.commit()
            session.refresh(profile)
            return profile

    def list_for_chat(self, telegram_chat_external_id: int) -> list[MonitorProfile]:
        with self.session_factory() as session:
            chat = TelegramChatRepository(session).get_by_telegram_id(telegram_chat_external_id)
            if chat is None:
                return []
            return list(MonitorProfileRepository(session).list_by_chat(chat.id))

    def list_recent(self, limit: int = 50) -> list[MonitorProfile]:
        with self.session_factory() as session:
            return list(MonitorProfileRepository(session).list_recent(limit))

    def get(self, monitor_profile_id: int) -> MonitorProfile | None:
        with self.session_factory() as session:
            return MonitorProfileRepository(session).get(monitor_profile_id)

    def pause(self, monitor_profile_id: int) -> MonitorProfile:
        return self._set_active(monitor_profile_id, is_active=False)

    def resume(self, monitor_profile_id: int) -> MonitorProfile:
        return self._set_active(monitor_profile_id, is_active=True)

    def delete(self, monitor_profile_id: int) -> None:
        with self.session_factory() as session:
            repo = MonitorProfileRepository(session)
            profile = repo.get(monitor_profile_id)
            if profile is None:
                raise ValueError(f"Monitor profile {monitor_profile_id} not found")
            repo.delete(profile)
            session.commit()

    def update_notifications(
        self,
        monitor_profile_id: int,
        *,
        instant_alerts_enabled: bool | None = None,
        digest_enabled: bool | None = None,
        priority_mode: str | None = None,
    ) -> MonitorProfile:
        with self.session_factory() as session:
            repo = MonitorProfileRepository(session)
            profile = repo.get(monitor_profile_id)
            if profile is None:
                raise ValueError(f"Monitor profile {monitor_profile_id} not found")
            if instant_alerts_enabled is not None:
                profile.instant_alerts_enabled = instant_alerts_enabled
            if digest_enabled is not None:
                profile.digest_enabled = digest_enabled
            if priority_mode is not None:
                if priority_mode not in self.VALID_PRIORITY_MODES:
                    raise ValueError(f"Unsupported priority mode: {priority_mode}")
                profile.priority_mode = priority_mode
            profile.updated_at = utcnow()
            repo.save(profile)
            session.commit()
            session.refresh(profile)
            return profile

    def _set_active(self, monitor_profile_id: int, *, is_active: bool) -> MonitorProfile:
        with self.session_factory() as session:
            repo = MonitorProfileRepository(session)
            profile = repo.get(monitor_profile_id)
            if profile is None:
                raise ValueError(f"Monitor profile {monitor_profile_id} not found")
            profile.is_active = is_active
            profile.updated_at = utcnow()
            repo.save(profile)
            session.commit()
            session.refresh(profile)
            return profile
