from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.time import format_utc, format_utc_short, utcnow
from app.models.event import DetectedEvent
from app.models.telegram_chat import TelegramChat
from app.models.telegram_user import TelegramUser
from app.repositories.deliveries import NotificationDeliveryRepository
from app.repositories.events import EventRepository
from app.repositories.items import ItemRepository
from app.repositories.monitor_matches import MonitorMatchRepository
from app.repositories.monitor_profiles import MonitorProfileRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.runs import RunRepository
from app.repositories.sources import SourceRepository
from app.repositories.summaries import AISummaryRepository
from app.repositories.telegram_registry import TelegramChatRepository, TelegramUserRepository
from app.services.monitor_runner import MonitorRunner, RunLockedError

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "web" / "templates")
)


def _search_query(request: Request) -> str:
    return request.query_params.get("q", "").strip()


def _query_value(request: Request, name: str) -> str:
    return request.query_params.get(name, "").strip()


def _query_int(request: Request, name: str) -> int | None:
    raw = _query_value(request, name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _query_bool(request: Request, name: str) -> bool | None:
    raw = _query_value(request, name).lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def _matches_query(query: str, *values: object) -> bool:
    if not query:
        return True

    lowered = query.lower()
    for value in values:
        if value is None:
            continue
        if lowered in str(value).lower():
            return True
    return False


def _active_filters(request: Request) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []
    for key, value in request.query_params.multi_items():
        if key == "q":
            continue
        filters.append(
            {
                "label": key.replace("_", " ").title(),
                "value": value,
            }
        )
    return filters


def _search_clear_url(request: Request) -> str:
    params = [(key, value) for key, value in request.query_params.multi_items() if key != "q"]
    if not params:
        return request.url.path
    return f"{request.url.path}?{urlencode(params)}"


def _app_settings(request: Request):
    return getattr(request.app.state, "settings", get_settings())


def _ensure_admin_write_enabled(request: Request) -> None:
    settings = _app_settings(request)
    if settings.admin_read_only_mode:
        raise HTTPException(status_code=403, detail="Admin is running in read-only demo mode")


def _base_context(request: Request) -> dict:
    settings = _app_settings(request)
    return {
        "request": request,
        "now": utcnow(),
        "app_name": settings.app_name,
        "admin_read_only_mode": settings.admin_read_only_mode,
        "integrations": {
            "telegram": bool(settings.telegram_bot_token and settings.telegram_chat_id),
            "bot_control": bool(
                settings.telegram_bot_control_enabled and settings.telegram_bot_token
            ),
            "gemini": bool(settings.gemini_api_key),
        },
        "fmt_price": lambda price: "n/a" if price is None else f"GBP {price:.2f}",
        "fmt_dt": format_utc,
        "fmt_dt_short": format_utc_short,
        "fmt_duration": lambda ms: f"{((ms or 0) / 1000):.1f}s",
        "fmt_ratio": lambda value: "n/a" if value is None else f"{value:.2f}",
        "search_query": _search_query(request),
        "active_filters": _active_filters(request),
        "persistent_query_params": [
            (key, value) for key, value in request.query_params.multi_items() if key != "q"
        ],
        "search_clear_url": _search_clear_url(request),
    }


def _get_runner(request: Request) -> MonitorRunner:
    return request.app.state.runner


def _get_run_dispatcher(request: Request):
    return request.app.state.run_dispatcher


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    source_repo = SourceRepository(session)
    run_repo = RunRepository(session)
    event_repo = EventRepository(session)
    summary_repo = AISummaryRepository(session)

    sources = source_repo.list_sources()
    recent_runs = run_repo.list_recent(limit=8)
    recent_events = event_repo.list_recent(limit=10)
    latest_summary = summary_repo.latest_for_source(sources[0].id) if sources else None
    query = _search_query(request)
    sources_by_id = {source.id: source for source in sources}
    if query:
        sources = [
            source
            for source in sources
            if _matches_query(
                query,
                source.name,
                source.slug,
                source.parser_key,
                source.base_url,
                source.start_url,
                source.health_status,
            )
        ]
        recent_runs = [
            run
            for run in recent_runs
            if _matches_query(
                query,
                run.id,
                run.status,
                run.trigger_type,
                run.error_message,
                sources_by_id.get(run.source_id).name if run.source_id in sources_by_id else None,
            )
        ]
        recent_events = [
            event
            for event in recent_events
            if _matches_query(
                query,
                event.event_type,
                event.severity,
                event.summary_text,
                sources_by_id.get(event.source_id).name
                if event.source_id in sources_by_id
                else None,
            )
        ]
        if latest_summary and not _matches_query(
            query, latest_summary.summary_text, latest_summary.highlights_json
        ):
            latest_summary = None

    active_item_count = sum(
        ItemRepository(session).count_active_by_source(source.id) for source in sources
    )
    health_counts = {
        "healthy": len([source for source in sources if source.health_status == "healthy"]),
        "degraded": len([source for source in sources if source.health_status == "degraded"]),
        "failing": len([source for source in sources if source.health_status == "failing"]),
    }
    success_rate = (
        round(
            (len([run for run in recent_runs if run.status == "succeeded"]) / len(recent_runs))
            * 100,
            1,
        )
        if recent_runs
        else 0.0
    )

    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            **_base_context(request),
            "sources": sources,
            "recent_runs": recent_runs,
            "recent_events": recent_events,
            "latest_summary": latest_summary,
            "health_counts": health_counts,
            "stats": {
                "sources": len(sources),
                "active_sources": len([source for source in sources if source.is_active]),
                "active_items": active_item_count,
                "recent_runs": len(recent_runs),
                "recent_events": len(recent_events),
                "high_events": len([event for event in recent_events if event.severity == "high"]),
                "success_rate": success_rate,
            },
        },
    )


@router.get("/sources", response_class=HTMLResponse)
def sources_list(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    source_repo = SourceRepository(session)
    sources = source_repo.list_sources()
    query = _search_query(request)
    health_filter = _query_value(request, "health")
    state_filter = _query_value(request, "state")
    schedule_filter = _query_value(request, "schedule")
    attention_filter = _query_bool(request, "attention")

    if health_filter:
        sources = [source for source in sources if source.health_status == health_filter]
    if state_filter == "active":
        sources = [source for source in sources if source.is_active]
    elif state_filter == "paused":
        sources = [source for source in sources if not source.is_active]
    if schedule_filter == "enabled":
        sources = [source for source in sources if source.schedule_enabled]
    elif schedule_filter == "disabled":
        sources = [source for source in sources if not source.schedule_enabled]
    if attention_filter:
        sources = [
            source
            for source in sources
            if source.health_status == "failing" or not source.is_active
        ]

    if query:
        sources = [
            source
            for source in sources
            if _matches_query(
                query,
                source.name,
                source.slug,
                source.parser_key,
                source.base_url,
                source.start_url,
                source.health_status,
            )
        ]
    item_repo = ItemRepository(session)
    active_item_counts = {
        source.id: item_repo.count_active_by_source(source.id) for source in sources
    }
    health_counts = {
        "healthy": len([source for source in sources if source.health_status == "healthy"]),
        "degraded": len([source for source in sources if source.health_status == "degraded"]),
        "failing": len([source for source in sources if source.health_status == "failing"]),
        "paused": len([source for source in sources if not source.is_active]),
    }
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            **_base_context(request),
            "sources": sources,
            "active_item_counts": active_item_counts,
            "health_counts": health_counts,
        },
    )


@router.get("/sources/{source_id}", response_class=HTMLResponse)
def source_detail(
    source_id: int, request: Request, session: Session = Depends(get_db_session)
) -> HTMLResponse:
    source_repo = SourceRepository(session)
    run_repo = RunRepository(session)
    event_repo = EventRepository(session)
    summary_repo = AISummaryRepository(session)
    item_repo = ItemRepository(session)

    source = source_repo.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    query = _search_query(request)
    runs = run_repo.list_recent_by_source(source_id, limit=10)
    recent_events = [
        event for event in event_repo.list_recent(limit=50) if event.source_id == source_id
    ][:10]
    run_status_filter = _query_value(request, "run_status")
    severity_filter = _query_value(request, "severity")
    event_type_filter = _query_value(request, "event_type")
    suppressed_filter = _query_bool(request, "suppressed")

    if run_status_filter:
        runs = [run for run in runs if run.status == run_status_filter]
    if severity_filter:
        recent_events = [event for event in recent_events if event.severity == severity_filter]
    if event_type_filter:
        recent_events = [event for event in recent_events if event.event_type == event_type_filter]
    if suppressed_filter is not None:
        recent_events = [
            event for event in recent_events if event.is_suppressed is suppressed_filter
        ]

    if query:
        runs = [
            run
            for run in runs
            if _matches_query(
                query,
                run.id,
                run.status,
                run.trigger_type,
                run.error_message,
            )
        ]
        recent_events = [
            event
            for event in recent_events
            if _matches_query(query, event.event_type, event.severity, event.summary_text)
        ]
        latest_summary = summary_repo.latest_for_source(source_id)
        if latest_summary and not _matches_query(
            query, latest_summary.summary_text, latest_summary.highlights_json
        ):
            latest_summary = None
    else:
        latest_summary = summary_repo.latest_for_source(source_id)

    finding_counts = {
        "high": len([event for event in recent_events if event.severity == "high"]),
        "medium": len([event for event in recent_events if event.severity == "medium"]),
        "low": len([event for event in recent_events if event.severity == "low"]),
    }
    return templates.TemplateResponse(
        request,
        "source_detail.html",
        {
            **_base_context(request),
            "source": source,
            "runs": runs,
            "latest_run": runs[0] if runs else None,
            "events": recent_events,
            "summary": latest_summary,
            "active_item_count": item_repo.count_active_by_source(source_id),
            "finding_counts": finding_counts,
        },
    )


@router.get("/items", response_class=HTMLResponse)
def items_list(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    item_repo = ItemRepository(session)
    source_repo = SourceRepository(session)

    items = list(item_repo.list_recent())
    sources = {source.id: source for source in source_repo.list_sources()}
    query = _search_query(request)
    source_filter = _query_int(request, "source_id")
    state_filter = _query_value(request, "state")
    availability_filter = _query_value(request, "availability")
    rating_filter = _query_value(request, "rating")

    if source_filter is not None:
        items = [item for item in items if item.source_id == source_filter]
    if state_filter == "active":
        items = [item for item in items if item.is_active]
    elif state_filter == "removed":
        items = [item for item in items if not item.is_active]
    if availability_filter:
        items = [item for item in items if item.availability_status == availability_filter]
    if rating_filter:
        items = [item for item in items if (item.rating or "") == rating_filter]
    if query:
        items = [
            item
            for item in items
            if _matches_query(
                query,
                item.title,
                item.source_item_key,
                item.canonical_url,
                item.external_id,
                item.availability_status,
                item.rating,
                sources.get(item.source_id).name if item.source_id in sources else None,
            )
        ]

    item_stats = {
        "total": len(items),
        "active": len([item for item in items if item.is_active]),
        "removed": len([item for item in items if not item.is_active]),
        "in_stock": len([item for item in items if item.availability_status == "in_stock"]),
    }
    return templates.TemplateResponse(
        request,
        "items.html",
        {
            **_base_context(request),
            "items": items,
            "sources": sources,
            "item_stats": item_stats,
        },
    )


@router.get("/items/{item_id}", response_class=HTMLResponse)
def item_detail(
    item_id: int, request: Request, session: Session = Depends(get_db_session)
) -> HTMLResponse:
    item_repo = ItemRepository(session)
    source_repo = SourceRepository(session)
    event_repo = EventRepository(session)

    item = item_repo.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    source = source_repo.get(item.source_id)
    snapshots = list(item_repo.list_snapshots(item_id, limit=12))
    events = list(event_repo.list_recent_by_item(item_id, limit=20))
    query = _search_query(request)
    severity_filter = _query_value(request, "severity")
    event_type_filter = _query_value(request, "event_type")
    suppressed_filter = _query_bool(request, "suppressed")

    if severity_filter:
        events = [event for event in events if event.severity == severity_filter]
    if event_type_filter:
        events = [event for event in events if event.event_type == event_type_filter]
    if suppressed_filter is not None:
        events = [event for event in events if event.is_suppressed is suppressed_filter]
    if query:
        snapshots = [
            snapshot
            for snapshot in snapshots
            if _matches_query(
                query,
                snapshot.title,
                snapshot.price_amount,
                snapshot.availability_status,
                snapshot.rating,
            )
        ]
        events = [
            event
            for event in events
            if _matches_query(query, event.event_type, event.severity, event.summary_text)
        ]

    event_stats = {
        "total": len(events),
        "high": len([event for event in events if event.severity == "high"]),
        "suppressed": len([event for event in events if event.is_suppressed]),
        "snapshots": len(snapshots),
    }
    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {
            **_base_context(request),
            "item": item,
            "source": source,
            "snapshots": snapshots,
            "events": events,
            "event_stats": event_stats,
        },
    )


@router.get("/monitors", response_class=HTMLResponse)
def monitors_list(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    monitor_repo = MonitorProfileRepository(session)
    source_repo = SourceRepository(session)
    user_repo = TelegramUserRepository(session)
    chat_repo = TelegramChatRepository(session)

    profiles = list(monitor_repo.list_recent(limit=60))
    sources = {source.id: source for source in source_repo.list_sources()}
    users = {user.id: user for user in user_repo.list_recent(limit=200)}
    chats = {chat.id: chat for chat in chat_repo.list_recent(limit=200)}
    query = _search_query(request)
    source_filter = _query_int(request, "source_id")
    state_filter = _query_value(request, "state")
    priority_filter = _query_value(request, "priority_mode")
    instant_filter = _query_bool(request, "instant")
    digest_filter = _query_bool(request, "digest")

    if source_filter is not None:
        profiles = [profile for profile in profiles if profile.source_id == source_filter]
    if state_filter == "active":
        profiles = [profile for profile in profiles if profile.is_active]
    elif state_filter == "paused":
        profiles = [profile for profile in profiles if not profile.is_active]
    if priority_filter:
        profiles = [profile for profile in profiles if profile.priority_mode == priority_filter]
    if instant_filter is not None:
        profiles = [
            profile for profile in profiles if profile.instant_alerts_enabled is instant_filter
        ]
    if digest_filter is not None:
        profiles = [profile for profile in profiles if profile.digest_enabled is digest_filter]
    if query:
        profiles = [
            profile
            for profile in profiles
            if _matches_query(
                query,
                profile.name,
                profile.category,
                profile.priority_mode,
                sources.get(profile.source_id).name if profile.source_id in sources else None,
                chats.get(profile.telegram_chat_id).title
                if profile.telegram_chat_id in chats
                else None,
                users.get(profile.telegram_user_id).username
                if profile.telegram_user_id in users
                else None,
            )
        ]

    monitor_stats = {
        "total": len(profiles),
        "active": len([profile for profile in profiles if profile.is_active]),
        "instant": len([profile for profile in profiles if profile.instant_alerts_enabled]),
        "digest": len([profile for profile in profiles if profile.digest_enabled]),
    }
    return templates.TemplateResponse(
        request,
        "monitors.html",
        {
            **_base_context(request),
            "profiles": profiles,
            "sources": sources,
            "users": users,
            "chats": chats,
            "monitor_stats": monitor_stats,
        },
    )


@router.get("/monitors/{monitor_id}", response_class=HTMLResponse)
def monitor_detail(
    monitor_id: int, request: Request, session: Session = Depends(get_db_session)
) -> HTMLResponse:
    monitor_repo = MonitorProfileRepository(session)
    match_repo = MonitorMatchRepository(session)
    delivery_repo = NotificationDeliveryRepository(session)
    source_repo = SourceRepository(session)
    run_repo = RunRepository(session)

    profile = monitor_repo.get(monitor_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Monitor profile not found")

    query = _search_query(request)
    priority_filter = _query_value(request, "priority")
    delivery_status_filter = _query_value(request, "delivery_status")
    delivery_type_filter = _query_value(request, "delivery_type")

    matches = list(match_repo.list_by_monitor(monitor_id, limit=40))
    deliveries = list(delivery_repo.list_by_monitor(monitor_id, limit=40))
    if priority_filter:
        matches = [match for match in matches if match.priority == priority_filter]
    if delivery_status_filter:
        deliveries = [
            delivery for delivery in deliveries if delivery.status == delivery_status_filter
        ]
    if delivery_type_filter:
        deliveries = [
            delivery for delivery in deliveries if delivery.delivery_type == delivery_type_filter
        ]

    events = {
        match.detected_event_id: session.get(DetectedEvent, match.detected_event_id)
        for match in matches
        if match.detected_event_id
    }
    runs = {
        match.monitoring_run_id: run_repo.get(match.monitoring_run_id)
        for match in matches
        if match.monitoring_run_id
    }
    if query:
        matches = [
            match
            for match in matches
            if _matches_query(
                query,
                match.match_reason,
                match.priority,
                events.get(match.detected_event_id).summary_text
                if match.detected_event_id in events and events.get(match.detected_event_id)
                else None,
            )
        ]
        deliveries = [
            delivery
            for delivery in deliveries
            if _matches_query(
                query,
                delivery.delivery_type,
                delivery.status,
                delivery.message_preview,
                delivery.error_text,
            )
        ]

    return templates.TemplateResponse(
        request,
        "monitor_detail.html",
        {
            **_base_context(request),
            "profile": profile,
            "source": source_repo.get(profile.source_id),
            "telegram_user": session.get(TelegramUser, profile.telegram_user_id),
            "telegram_chat": session.get(TelegramChat, profile.telegram_chat_id),
            "matches": matches,
            "deliveries": deliveries,
            "events": events,
            "runs": runs,
            "match_stats": {
                "total": len(matches),
                "high": len([match for match in matches if match.priority == "high"]),
                "medium": len([match for match in matches if match.priority == "medium"]),
                "deliveries": len(deliveries),
            },
        },
    )


@router.get("/deliveries", response_class=HTMLResponse)
def deliveries(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    delivery_repo = NotificationDeliveryRepository(session)
    monitor_repo = MonitorProfileRepository(session)
    chat_repo = TelegramChatRepository(session)

    deliveries = list(delivery_repo.list_recent(limit=80))
    profiles = {profile.id: profile for profile in monitor_repo.list_recent(limit=200)}
    chats = {chat.id: chat for chat in chat_repo.list_recent(limit=200)}
    query = _search_query(request)
    status_filter = _query_value(request, "status")
    delivery_type_filter = _query_value(request, "delivery_type")
    monitor_filter = _query_int(request, "monitor_id")
    chat_filter = _query_int(request, "chat_id")

    if status_filter:
        deliveries = [delivery for delivery in deliveries if delivery.status == status_filter]
    if delivery_type_filter:
        deliveries = [
            delivery for delivery in deliveries if delivery.delivery_type == delivery_type_filter
        ]
    if monitor_filter is not None:
        deliveries = [
            delivery for delivery in deliveries if delivery.monitor_profile_id == monitor_filter
        ]
    if chat_filter is not None:
        deliveries = [
            delivery for delivery in deliveries if delivery.telegram_chat_id == chat_filter
        ]
    if query:
        deliveries = [
            delivery
            for delivery in deliveries
            if _matches_query(
                query,
                delivery.delivery_type,
                delivery.status,
                delivery.message_preview,
                delivery.error_text,
                profiles.get(delivery.monitor_profile_id).name
                if delivery.monitor_profile_id in profiles
                else None,
                chats.get(delivery.telegram_chat_id).title
                if delivery.telegram_chat_id in chats
                else None,
            )
        ]

    delivery_stats = {
        "total": len(deliveries),
        "sent": len([delivery for delivery in deliveries if delivery.status == "sent"]),
        "failed": len([delivery for delivery in deliveries if delivery.status == "failed"]),
        "suppressed": len([delivery for delivery in deliveries if delivery.status == "suppressed"]),
    }
    return templates.TemplateResponse(
        request,
        "deliveries.html",
        {
            **_base_context(request),
            "deliveries": deliveries,
            "profiles": profiles,
            "chats": chats,
            "delivery_stats": delivery_stats,
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
    run_repo = RunRepository(session)
    source_repo = SourceRepository(session)
    runs = run_repo.list_recent(limit=30)
    sources = {source.id: source for source in source_repo.list_sources()}
    query = _search_query(request)
    status_filter = _query_value(request, "status")
    trigger_filter = _query_value(request, "trigger")
    source_filter = _query_int(request, "source_id")

    if status_filter:
        runs = [run for run in runs if run.status == status_filter]
    if trigger_filter:
        runs = [run for run in runs if run.trigger_type == trigger_filter]
    if source_filter is not None:
        runs = [run for run in runs if run.source_id == source_filter]

    if query:
        runs = [
            run
            for run in runs
            if _matches_query(
                query,
                run.id,
                run.status,
                run.trigger_type,
                run.error_message,
                sources.get(run.source_id).name if run.source_id in sources else None,
            )
        ]
    run_stats = {
        "total": len(runs),
        "succeeded": len([run for run in runs if run.status == "succeeded"]),
        "degraded": len([run for run in runs if run.status == "degraded"]),
        "failed": len([run for run in runs if run.status == "failed"]),
    }
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            **_base_context(request),
            "runs": runs,
            "sources": sources,
            "run_stats": run_stats,
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(
    run_id: int, request: Request, session: Session = Depends(get_db_session)
) -> HTMLResponse:
    run_repo = RunRepository(session)
    source_repo = SourceRepository(session)
    event_repo = EventRepository(session)
    notification_repo = NotificationRepository(session)
    delivery_repo = NotificationDeliveryRepository(session)
    profile_repo = MonitorProfileRepository(session)
    summary_repo = AISummaryRepository(session)

    run = run_repo.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    query = _search_query(request)
    events = event_repo.list_by_run(run_id)
    notifications = notification_repo.list_by_run(run_id)
    monitor_deliveries = list(delivery_repo.list_by_run(run_id))
    monitor_profiles = {
        delivery.monitor_profile_id: profile_repo.get(delivery.monitor_profile_id)
        for delivery in monitor_deliveries
        if delivery.monitor_profile_id
    }
    delivery_chats = {
        delivery.telegram_chat_id: session.get(TelegramChat, delivery.telegram_chat_id)
        for delivery in monitor_deliveries
        if delivery.telegram_chat_id
    }
    summary = summary_repo.by_run(run_id)
    severity_filter = _query_value(request, "severity")
    event_type_filter = _query_value(request, "event_type")
    suppressed_filter = _query_bool(request, "suppressed")
    notification_status_filter = _query_value(request, "notification_status")
    notification_type_filter = _query_value(request, "notification_type")
    delivery_status_filter = _query_value(request, "delivery_status")
    delivery_type_filter = _query_value(request, "delivery_type")

    if severity_filter:
        events = [event for event in events if event.severity == severity_filter]
    if event_type_filter:
        events = [event for event in events if event.event_type == event_type_filter]
    if suppressed_filter is not None:
        events = [event for event in events if event.is_suppressed is suppressed_filter]
    if notification_status_filter:
        notifications = [
            notification
            for notification in notifications
            if notification.status == notification_status_filter
        ]
    if notification_type_filter:
        notifications = [
            notification
            for notification in notifications
            if notification.notification_type == notification_type_filter
        ]
    if delivery_status_filter:
        monitor_deliveries = [
            delivery for delivery in monitor_deliveries if delivery.status == delivery_status_filter
        ]
    if delivery_type_filter:
        monitor_deliveries = [
            delivery
            for delivery in monitor_deliveries
            if delivery.delivery_type == delivery_type_filter
        ]

    if query:
        events = [
            event
            for event in events
            if _matches_query(query, event.event_type, event.severity, event.summary_text)
        ]
        notifications = [
            notification
            for notification in notifications
            if _matches_query(
                query,
                notification.notification_type,
                notification.status,
                notification.payload_preview,
                notification.error_message,
                notification.destination,
            )
        ]
        monitor_deliveries = [
            delivery
            for delivery in monitor_deliveries
            if _matches_query(
                query,
                delivery.delivery_type,
                delivery.status,
                delivery.message_preview,
                delivery.error_text,
                monitor_profiles.get(delivery.monitor_profile_id).name
                if delivery.monitor_profile_id in monitor_profiles
                and monitor_profiles.get(delivery.monitor_profile_id)
                else None,
                delivery_chats.get(delivery.telegram_chat_id).title
                if delivery.telegram_chat_id in delivery_chats
                and delivery_chats.get(delivery.telegram_chat_id)
                else None,
            )
        ]
        if summary and not _matches_query(
            query, summary.summary_text, summary.highlights_json, summary.status
        ):
            summary = None

    event_stats = {
        "total": len(events),
        "suppressed": len([event for event in events if event.is_suppressed]),
        "high": len([event for event in events if event.severity == "high"]),
        "alerts": len(
            [notification for notification in notifications if notification.status == "sent"]
        ),
        "monitor_deliveries": len(monitor_deliveries),
    }
    source = source_repo.get(run.source_id)
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            **_base_context(request),
            "run": run,
            "source": source,
            "events": events,
            "notifications": notifications,
            "monitor_deliveries": monitor_deliveries,
            "monitor_profiles": monitor_profiles,
            "delivery_chats": delivery_chats,
            "summary": summary,
            "event_stats": event_stats,
        },
    )


@router.get("/findings", response_class=HTMLResponse)
def findings(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    event_repo = EventRepository(session)
    source_repo = SourceRepository(session)
    run_filter = _query_int(request, "run_id")
    events = (
        event_repo.list_by_run(run_filter)
        if run_filter is not None
        else event_repo.list_recent(limit=40)
    )
    sources = {source.id: source for source in source_repo.list_sources()}
    query = _search_query(request)
    severity_filter = _query_value(request, "severity")
    event_type_filter = _query_value(request, "event_type")
    source_filter = _query_int(request, "source_id")
    suppressed_filter = _query_bool(request, "suppressed")

    if severity_filter:
        events = [event for event in events if event.severity == severity_filter]
    if event_type_filter:
        events = [event for event in events if event.event_type == event_type_filter]
    if source_filter is not None:
        events = [event for event in events if event.source_id == source_filter]
    if suppressed_filter is not None:
        events = [event for event in events if event.is_suppressed is suppressed_filter]

    if query:
        events = [
            event
            for event in events
            if _matches_query(
                query,
                event.event_type,
                event.severity,
                event.summary_text,
                sources.get(event.source_id).name if event.source_id in sources else None,
            )
        ]
    finding_stats = {
        "total": len(events),
        "high": len([event for event in events if event.severity == "high"]),
        "medium": len([event for event in events if event.severity == "medium"]),
        "low": len([event for event in events if event.severity == "low"]),
        "suppressed": len([event for event in events if event.is_suppressed]),
    }
    return templates.TemplateResponse(
        request,
        "findings.html",
        {
            **_base_context(request),
            "events": events,
            "sources": sources,
            "finding_stats": finding_stats,
        },
    )
