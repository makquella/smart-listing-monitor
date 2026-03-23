from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin as admin_api
from app.api import api as api_api
from app.bot.main import TelegramBotController
from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import configure_logging
from app.core.scheduler import SchedulerService
from app.repositories.sources import SourceRepository
from app.services.monitor_runner import MonitorRunner, build_runner_dependencies
from app.services.run_dispatcher import RunDispatcher


def build_runner() -> MonitorRunner:
    settings = get_settings()
    dependencies = build_runner_dependencies(settings)
    return MonitorRunner(**dependencies)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()

    from app.core.db import SessionLocal

    with SessionLocal() as session:
        SourceRepository(session).ensure_seed_source(settings)

    runner = build_runner()
    dispatcher = RunDispatcher(runner=runner)
    scheduler = SchedulerService(session_factory=runner.session_factory, runner=runner)
    scheduler.start()
    bot_controller = TelegramBotController(
        settings=settings, session_factory=runner.session_factory, runner=runner
    )
    bot_controller.start()

    app.state.runner = runner
    app.state.run_dispatcher = dispatcher
    app.state.scheduler = scheduler
    app.state.bot_controller = bot_controller
    yield
    scheduler.shutdown()
    dispatcher.shutdown()
    await bot_controller.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="Parset Monitor", lifespan=lifespan)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).resolve().parent / "web" / "static")),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/admin")

    app.include_router(admin_api.router, prefix="/admin", tags=["admin"])
    app.include_router(api_api.router, tags=["api"])
    return app


app = create_app()
