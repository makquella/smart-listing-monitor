import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.sources import SourceRepository
from app.services.monitor_runner import MonitorRunner, RunLockedError


logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, *, session_factory: sessionmaker[Session], runner: MonitorRunner):
        self.session_factory = session_factory
        self.runner = runner
        self.scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        self.sync_jobs()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def sync_jobs(self) -> None:
        with self.session_factory() as session:
            source_repo = SourceRepository(session)
            sources = source_repo.list_scheduled_sources()

        desired_job_ids = {f"monitor-source-{source.id}" for source in sources}
        for job in list(self.scheduler.get_jobs()):
            if job.id not in desired_job_ids:
                self.scheduler.remove_job(job.id)

        for source in sources:
            self.scheduler.add_job(
                self._run_safely,
                "interval",
                minutes=source.schedule_interval_minutes,
                id=f"monitor-source-{source.id}",
                replace_existing=True,
                kwargs={"source_id": source.id},
            )

    def _run_safely(self, source_id: int) -> None:
        try:
            self.runner.run_source(source_id, trigger_type="scheduled")
        except RunLockedError:
            logger.info("Skipped scheduled run for source %s because a run is already in progress", source_id)
        except Exception:
            logger.exception("Scheduled run failed for source %s", source_id)
