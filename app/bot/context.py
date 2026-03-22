from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.services.monitor_profiles import MonitorProfileService
from app.services.monitor_runner import MonitorRunner


@dataclass(slots=True)
class BotServices:
    session_factory: sessionmaker[Session]
    runner: MonitorRunner
    monitor_profiles: MonitorProfileService


_services: BotServices | None = None


def set_bot_services(services: BotServices) -> None:
    global _services
    _services = services


def get_bot_services() -> BotServices:
    if _services is None:
        raise RuntimeError("Bot services are not initialized")
    return _services
