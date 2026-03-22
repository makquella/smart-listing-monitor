from collections import defaultdict
from contextlib import contextmanager
import threading


class SourceRunLockManager:
    """Single-process per-source locking for the MVP."""

    def __init__(self) -> None:
        self._locks: dict[int, threading.Lock] = defaultdict(threading.Lock)

    def acquire(self, source_id: int) -> bool:
        return self._locks[source_id].acquire(blocking=False)

    def release(self, source_id: int) -> None:
        lock = self._locks[source_id]
        if lock.locked():
            lock.release()

    @contextmanager
    def held(self, source_id: int):
        acquired = self.acquire(source_id)
        try:
            yield acquired
        finally:
            if acquired:
                self.release(source_id)
