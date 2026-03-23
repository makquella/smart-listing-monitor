import pytest

from app.core.config import Settings
from app.core.runtime import RuntimeModeError, detect_multi_process_probe, enforce_runtime_mode


def test_detect_multi_process_probe_reads_web_concurrency() -> None:
    probe = detect_multi_process_probe({"WEB_CONCURRENCY": "3"})

    assert probe is not None
    assert probe.worker_count == 3
    assert probe.source == "WEB_CONCURRENCY"


def test_detect_multi_process_probe_reads_gunicorn_workers() -> None:
    probe = detect_multi_process_probe({"GUNICORN_CMD_ARGS": "--bind 0.0.0.0:8000 --workers 4"})

    assert probe is not None
    assert probe.worker_count == 4
    assert probe.source == "GUNICORN_CMD_ARGS"


def test_enforce_runtime_mode_allows_single_process_defaults() -> None:
    settings = Settings(_env_file=None)

    enforce_runtime_mode(settings, environ={})


def test_enforce_runtime_mode_blocks_detected_multi_worker_runtime() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(RuntimeModeError):
        enforce_runtime_mode(settings, environ={"UVICORN_WORKERS": "2"})


def test_enforce_runtime_mode_can_be_overridden_for_experiments() -> None:
    settings = Settings(_env_file=None, ALLOW_UNSAFE_MULTI_PROCESS_RUNTIME=True)

    enforce_runtime_mode(settings, environ={"WEB_CONCURRENCY": "2"})
