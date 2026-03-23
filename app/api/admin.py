from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db_session
from app.repositories.sources import SourceRepository
from app.services.monitor_runner import RunLockedError
from app.web.context import app_settings, build_base_context
from app.web.page_builders import (
    build_deliveries_page,
    build_findings_page,
    build_item_detail_page,
    build_items_page,
    build_monitor_detail_page,
    build_monitors_page,
    build_overview_page,
    build_run_detail_page,
    build_runs_page,
    build_source_detail_page,
    build_sources_page,
)
from app.web.params import (
    DeliveriesPageParams,
    FindingsPageParams,
    ItemDetailPageParams,
    ItemsPageParams,
    MonitorDetailPageParams,
    MonitorsPageParams,
    OverviewPageParams,
    RunDetailPageParams,
    RunsPageParams,
    SourceDetailPageParams,
    SourcesPageParams,
)

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "web" / "templates")
)


def _ensure_admin_write_enabled(request: Request) -> None:
    settings = app_settings(request)
    if settings.admin_read_only_mode:
        raise HTTPException(status_code=403, detail="Admin is running in read-only demo mode")


def _base_context(request: Request) -> dict:
    return build_base_context(request)


def _get_run_dispatcher(request: Request):
    return request.app.state.run_dispatcher


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    params = OverviewPageParams.from_request(request)
    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            **_base_context(request),
            **build_overview_page(session, params),
        },
    )


@router.get("/sources", response_class=HTMLResponse)
def sources_list(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    params = SourcesPageParams.from_request(request)
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            **_base_context(request),
            **build_sources_page(session, params),
        },
    )


@router.get("/sources/{source_id}", response_class=HTMLResponse)
def source_detail(
    source_id: int, request: Request, session: Session = Depends(get_db_session)
) -> HTMLResponse:
    params = SourceDetailPageParams.from_request(request)
    try:
        page = build_source_detail_page(session, source_id=source_id, params=params)
    except LookupError:
        raise HTTPException(status_code=404, detail="Source not found")
    return templates.TemplateResponse(
        request,
        "source_detail.html",
        {
            **_base_context(request),
            **page,
        },
    )


@router.get("/items", response_class=HTMLResponse)
def items_list(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    params = ItemsPageParams.from_request(request)
    return templates.TemplateResponse(
        request,
        "items.html",
        {
            **_base_context(request),
            **build_items_page(session, params),
        },
    )


@router.get("/items/{item_id}", response_class=HTMLResponse)
def item_detail(
    item_id: int, request: Request, session: Session = Depends(get_db_session)
) -> HTMLResponse:
    params = ItemDetailPageParams.from_request(request)
    try:
        page = build_item_detail_page(session, item_id=item_id, params=params)
    except LookupError:
        raise HTTPException(status_code=404, detail="Item not found")
    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {
            **_base_context(request),
            **page,
        },
    )


@router.get("/monitors", response_class=HTMLResponse)
def monitors_list(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    params = MonitorsPageParams.from_request(request)
    return templates.TemplateResponse(
        request,
        "monitors.html",
        {
            **_base_context(request),
            **build_monitors_page(session, params),
        },
    )


@router.get("/monitors/{monitor_id}", response_class=HTMLResponse)
def monitor_detail(
    monitor_id: int, request: Request, session: Session = Depends(get_db_session)
) -> HTMLResponse:
    params = MonitorDetailPageParams.from_request(request)
    try:
        page = build_monitor_detail_page(session, monitor_id=monitor_id, params=params)
    except LookupError:
        raise HTTPException(status_code=404, detail="Monitor profile not found")
    return templates.TemplateResponse(
        request,
        "monitor_detail.html",
        {
            **_base_context(request),
            **page,
        },
    )


@router.get("/deliveries", response_class=HTMLResponse)
def deliveries(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    params = DeliveriesPageParams.from_request(request)
    return templates.TemplateResponse(
        request,
        "deliveries.html",
        {
            **_base_context(request),
            **build_deliveries_page(session, params),
        },
    )


@router.post("/sources/{source_id}/run")
def run_source(
    source_id: int, request: Request, dispatcher=Depends(_get_run_dispatcher)
) -> RedirectResponse:
    _ensure_admin_write_enabled(request)
    try:
        run = dispatcher.enqueue_source(source_id, trigger_type="manual")
    except RunLockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url=f"/admin/runs/{run.id}", status_code=303)


@router.post("/sources/{source_id}/settings")
def update_source_settings(
    source_id: int,
    request: Request,
    schedule_enabled: bool = Form(False),
    is_active: bool = Form(False),
    schedule_interval_minutes: int = Form(...),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    _ensure_admin_write_enabled(request)
    source_repo = SourceRepository(session)
    source = source_repo.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    source_repo.update_schedule(
        source,
        schedule_enabled=schedule_enabled,
        is_active=is_active,
        schedule_interval_minutes=max(schedule_interval_minutes, 5),
    )
    request.app.state.scheduler.sync_jobs()
    return RedirectResponse(url=f"/admin/sources/{source_id}", status_code=303)


@router.get("/runs", response_class=HTMLResponse)
def runs_list(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    params = RunsPageParams.from_request(request)
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            **_base_context(request),
            **build_runs_page(session, params),
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(
    run_id: int, request: Request, session: Session = Depends(get_db_session)
) -> HTMLResponse:
    params = RunDetailPageParams.from_request(request)
    try:
        page = build_run_detail_page(session, run_id=run_id, params=params)
    except LookupError:
        raise HTTPException(status_code=404, detail="Run not found")
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            **_base_context(request),
            **page,
        },
    )


@router.get("/findings", response_class=HTMLResponse)
def findings(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    params = FindingsPageParams.from_request(request)
    return templates.TemplateResponse(
        request,
        "findings.html",
        {
            **_base_context(request),
            **build_findings_page(session, params),
        },
    )
