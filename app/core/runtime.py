import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.core.config import Settings

logger = logging.getLogger(__name__)

_GUNICORN_WORKERS_RE = re.compile(r"(?:^|\s)(?:-w|--workers)(?:[=\s]+)(\d+)(?:\s|$)")


class RuntimeModeError(RuntimeError):
    """Raised when the process configuration conflicts with the runtime mode."""


@dataclass(slots=True, frozen=True)
class RuntimeProbe:
    worker_count: int
    source: str
    raw_value: str


def detect_multi_process_probe(environ: Mapping[str, str] | None = None) -> RuntimeProbe | None:
    env = environ or os.environ
    probes: list[RuntimeProbe] = []

    probes.extend(_probe_integer(env, "UVICORN_WORKERS", "UVICORN_WORKERS"))
    probes.extend(_probe_integer(env, "WEB_CONCURRENCY", "WEB_CONCURRENCY"))
    probes.extend(_probe_gunicorn_args(env.get("GUNICORN_CMD_ARGS")))

    if not probes:
        return None
    return max(probes, key=lambda probe: probe.worker_count)


def enforce_runtime_mode(settings: Settings, *, environ: Mapping[str, str] | None = None) -> None:
    runtime_mode = settings.runtime_mode.strip().lower()
    if runtime_mode != "single_process":
        logger.warning(
            "Unknown runtime mode '%s'; defaulting to single-process safeguards", runtime_mode
        )

    probe = detect_multi_process_probe(environ)
    if probe is None or probe.worker_count <= 1:
        logger.info(
            "Runtime mode: single_process. Scheduler, bot control, dispatcher, and source locks "
            "will run inside one app process."
        )
        return

    message = (
        "Single-process runtime requires one app process, but detected "
        f"{probe.source}={probe.raw_value!r}. Scheduler, Telegram bot control, "
        "background run dispatching, and in-memory source locks are only safe in a single process. "
        "Use one worker/process for demo deployment, or move to a shared coordination layer before "
        "running multi-worker or multi-host."
    )
    if settings.allow_unsafe_multi_process_runtime:
        logger.warning(
            "%s Proceeding because ALLOW_UNSAFE_MULTI_PROCESS_RUNTIME=true is set.", message
        )
        return
    raise RuntimeModeError(message)


def _probe_integer(env: Mapping[str, str], key: str, source: str) -> list[RuntimeProbe]:
    raw_value = env.get(key)
    if not raw_value:
        return []
    try:
        worker_count = int(raw_value)
    except ValueError:
        return []
    return [RuntimeProbe(worker_count=worker_count, source=source, raw_value=raw_value)]


def _probe_gunicorn_args(raw_value: str | None) -> list[RuntimeProbe]:
    if not raw_value:
        return []
    match = _GUNICORN_WORKERS_RE.search(raw_value)
    if match is None:
        return []
    return [
        RuntimeProbe(
            worker_count=int(match.group(1)),
            source="GUNICORN_CMD_ARGS",
            raw_value=raw_value,
        )
    ]
