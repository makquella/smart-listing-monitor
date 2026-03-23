from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import get_db_session
from app.main import create_app
from app.repositories.sources import SourceRepository


class DummyDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def enqueue_source(self, source_id: int, trigger_type: str = "manual") -> SimpleNamespace:
        self.calls.append((source_id, trigger_type))
        return SimpleNamespace(id=4242)


class DummyScheduler:
    def sync_jobs(self) -> None:
        return None


def _build_smoke_client(
    session_factory, *, read_only: bool = False
) -> tuple[TestClient, DummyDispatcher]:
    with session_factory() as session:
        SourceRepository(session).ensure_seed_source(Settings())

    app = create_app()
    dispatcher = DummyDispatcher()

    def override_get_db_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.state.settings = Settings(ADMIN_READ_ONLY_MODE=read_only)
    app.state.run_dispatcher = dispatcher
    app.state.scheduler = DummyScheduler()
    app.state.runner = SimpleNamespace()
    return TestClient(app), dispatcher


@pytest.fixture()
def smoke_client(session_factory) -> Generator[tuple[TestClient, DummyDispatcher], None, None]:
    client, dispatcher = _build_smoke_client(session_factory)
    yield client, dispatcher
    client.close()


@pytest.fixture()
def smoke_client_read_only(
    session_factory,
) -> Generator[tuple[TestClient, DummyDispatcher], None, None]:
    client, dispatcher = _build_smoke_client(session_factory, read_only=True)
    yield client, dispatcher
    client.close()


def test_admin_dashboard_opens(smoke_client) -> None:
    client, _ = smoke_client

    response = client.get("/admin/")

    assert response.status_code == 200
    assert "Parset" in response.text
    assert "Dashboard" in response.text


def test_source_detail_page_opens(smoke_client) -> None:
    client, _ = smoke_client

    response = client.get("/admin/sources/1")

    assert response.status_code == 200
    assert "Books to Scrape" in response.text
    assert "Source State" in response.text


def test_manual_run_endpoint_redirects_and_enqueues(smoke_client) -> None:
    client, dispatcher = smoke_client

    response = client.post("/admin/sources/1/run", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/runs/4242"
    assert dispatcher.calls == [(1, "manual")]


def test_admin_dashboard_shows_read_only_banner(smoke_client_read_only) -> None:
    client, _ = smoke_client_read_only

    response = client.get("/admin/")

    assert response.status_code == 200
    assert "Read-only mode is enabled" in response.text
    assert "Demo read-only" in response.text


def test_manual_run_endpoint_is_blocked_in_read_only_mode(smoke_client_read_only) -> None:
    client, dispatcher = smoke_client_read_only

    response = client.post("/admin/sources/1/run", follow_redirects=False)

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin is running in read-only demo mode"
    assert dispatcher.calls == []


def test_source_settings_endpoint_is_blocked_in_read_only_mode(
    smoke_client_read_only,
) -> None:
    client, _ = smoke_client_read_only

    response = client.post(
        "/admin/sources/1/settings",
        data={
            "schedule_interval_minutes": "15",
            "schedule_enabled": "on",
            "is_active": "on",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin is running in read-only demo mode"


@pytest.mark.parametrize("path", ["/api/runs", "/api/events"])
def test_api_endpoints_return_200(smoke_client, path: str) -> None:
    client, _ = smoke_client

    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
