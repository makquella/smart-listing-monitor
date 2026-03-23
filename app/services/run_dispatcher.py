import logging
from concurrent.futures import Future, ThreadPoolExecutor

from app.models.run import MonitoringRun
from app.services.monitor_runner import MonitorRunner

logger = logging.getLogger(__name__)


class RunDispatcher:
    def __init__(self, runner: MonitorRunner, max_workers: int = 2) -> None:
        self.runner = runner
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="parset-runner"
        )
        self._futures: set[Future] = set()

    def enqueue_source(self, source_id: int, trigger_type: str = "manual") -> MonitoringRun:
        run = self.runner.queue_run(source_id, trigger_type=trigger_type)
        future = self.executor.submit(self.runner.run_queued_run, run.id)
        self._futures.add(future)
        future.add_done_callback(self._finalize_future)
        return run

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def _finalize_future(self, future: Future) -> None:
        self._futures.discard(future)
        try:
            future.result()
        except Exception:
            logger.exception("Background monitoring run crashed")
