import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher
from sqlalchemy.orm import Session, sessionmaker

from app.bot.context import BotServices, set_bot_services
from app.bot.handlers import monitors, start, status
from app.core.config import Settings
from app.services.monitor_profiles import MonitorProfileService
from app.services.monitor_runner import MonitorRunner


class TelegramBotController:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        runner: MonitorRunner,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.runner = runner
        self.enabled = bool(settings.telegram_bot_control_enabled and settings.telegram_bot_token)
        self.bot = Bot(token=settings.telegram_bot_token) if settings.telegram_bot_token else None
        self.dispatcher = Dispatcher() if self.bot else None
        self._task: asyncio.Task | None = None

        if self.dispatcher is not None:
            self.dispatcher.include_router(start.router)
            self.dispatcher.include_router(monitors.router)
            self.dispatcher.include_router(status.router)
            set_bot_services(
                BotServices(
                    session_factory=session_factory,
                    runner=runner,
                    monitor_profiles=MonitorProfileService(session_factory),
                )
            )

    def start(self) -> None:
        if not self.enabled or self.bot is None or self.dispatcher is None or self._task is not None:
            return
        self._task = asyncio.create_task(
            self.dispatcher.start_polling(
                self.bot,
                polling_timeout=self.settings.telegram_bot_polling_timeout_seconds,
            )
        )

    async def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self.bot is not None:
            await self.bot.session.close()
