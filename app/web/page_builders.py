from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

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


def build_overview_page(session: Session, params: OverviewPageParams) -> dict[str, Any]:
    source_repo = SourceRepository(session)
    run_repo = RunRepository(session)
    event_repo = EventRepository(session)
    summary_repo = AISummaryRepository(session)
    match_repo = MonitorMatchRepository(session)
    delivery_repo = NotificationDeliveryRepository(session)
    item_repo = ItemRepository(session)

    sources = source_repo.list_for_admin(search_query=params.search_query)
    recent_runs = run_repo.list_for_admin(limit=8, search_query=params.search_query)
    recent_events = event_repo.list_for_admin(limit=6, search_query=params.search_query)
    sources_by_id = {source.id: source for source in source_repo.list_sources()}
    latest_summary = summary_repo.latest_for_source(sources[0].id) if sources else None
    if (
        latest_summary
        and params.search_query
        and not _matches_query(
            params.search_query, latest_summary.summary_text, latest_summary.highlights_json
        )
    ):
        latest_summary = None

    recent_matches = list(match_repo.list_recent(limit=12))
    recent_deliveries = list(delivery_repo.list_recent(limit=20))
    last_run = recent_runs[0] if recent_runs else None
    last_source_checked = sources_by_id.get(last_run.source_id) if last_run else None
    last_alert_sent = next(
        (delivery for delivery in recent_deliveries if delivery.status == "sent"),
        None,
    )
    last_monitor_match = recent_matches[0] if recent_matches else None
    active_item_count = sum(item_repo.count_active_by_source(source.id) for source in sources)
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

    return {
        "sources": sources,
        "recent_runs": recent_runs,
        "recent_events": recent_events,
        "latest_summary": latest_summary,
        "last_run": last_run,
        "last_source_checked": last_source_checked,
        "last_alert_sent": last_alert_sent,
        "last_monitor_match": last_monitor_match,
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
    }


def build_sources_page(session: Session, params: SourcesPageParams) -> dict[str, Any]:
    source_repo = SourceRepository(session)
    run_repo = RunRepository(session)
    event_repo = EventRepository(session)
    item_repo = ItemRepository(session)

    sources = source_repo.list_for_admin(
        health_status=params.health_status,
        is_active=params.is_active,
        schedule_enabled=params.schedule_enabled,
        attention_only=params.attention_only,
        search_query=params.search_query,
    )
    source_activity, source_activity_feed = _build_source_activity(
        sources,
        run_repo.list_recent(limit=40),
        event_repo.list_recent(limit=80),
    )
    active_item_counts = {
        source.id: item_repo.count_active_by_source(source.id) for source in sources
    }
    health_counts = {
        "healthy": len([source for source in sources if source.health_status == "healthy"]),
        "degraded": len([source for source in sources if source.health_status == "degraded"]),
        "failing": len([source for source in sources if source.health_status == "failing"]),
        "paused": len([source for source in sources if not source.is_active]),
    }
    return {
        "sources": sources,
        "active_item_counts": active_item_counts,
        "health_counts": health_counts,
        "source_activity": source_activity,
        "source_activity_feed": source_activity_feed,
    }


def build_source_detail_page(
    session: Session, *, source_id: int, params: SourceDetailPageParams
) -> dict[str, Any]:
    source_repo = SourceRepository(session)
    run_repo = RunRepository(session)
    event_repo = EventRepository(session)
    summary_repo = AISummaryRepository(session)
    item_repo = ItemRepository(session)
    delivery_repo = NotificationDeliveryRepository(session)

    source = source_repo.get(source_id)
    if source is None:
        raise LookupError("Source not found")

    runs = run_repo.list_for_admin(
        limit=10,
        status=params.run_status,
        source_id=source_id,
        search_query=params.search_query,
    )
    recent_events = event_repo.list_for_admin(
        limit=8,
        source_id=source_id,
        severity=params.severity,
        event_type=params.event_type,
        suppressed=params.suppressed,
        search_query=params.search_query,
    )
    latest_summary = summary_repo.latest_for_source(source_id)
    if (
        latest_summary
        and params.search_query
        and not _matches_query(
            params.search_query, latest_summary.summary_text, latest_summary.highlights_json
        )
    ):
        latest_summary = None

    latest_run = runs[0] if runs else None
    latest_run_outcome = (
        {
            "status": latest_run.status,
            "completeness": latest_run.parse_completeness_ratio,
            "alerts": latest_run.alerts_sent_count,
            "deliveries": len(delivery_repo.list_by_run(latest_run.id)),
        }
        if latest_run
        else None
    )
    finding_counts = {
        "high": len([event for event in recent_events if event.severity == "high"]),
        "medium": len([event for event in recent_events if event.severity == "medium"]),
        "low": len([event for event in recent_events if event.severity == "low"]),
    }
    return {
        "source": source,
        "runs": runs,
        "latest_run": latest_run,
        "latest_run_outcome": latest_run_outcome,
        "events": recent_events,
        "summary": latest_summary,
        "active_item_count": item_repo.count_active_by_source(source_id),
        "finding_counts": finding_counts,
    }


def build_items_page(session: Session, params: ItemsPageParams) -> dict[str, Any]:
    item_repo = ItemRepository(session)
    source_repo = SourceRepository(session)

    items = list(
        item_repo.list_for_admin(
            source_id=params.source_id,
            is_active=params.is_active,
            availability_status=params.availability_status,
            rating=params.rating,
            search_query=params.search_query,
        )
    )
    sources = {source.id: source for source in source_repo.list_sources()}
    item_stats = {
        "total": len(items),
        "active": len([item for item in items if item.is_active]),
        "removed": len([item for item in items if not item.is_active]),
        "in_stock": len([item for item in items if item.availability_status == "in_stock"]),
    }
    return {
        "items": items,
        "sources": sources,
        "item_stats": item_stats,
    }


def build_item_detail_page(
    session: Session, *, item_id: int, params: ItemDetailPageParams
) -> dict[str, Any]:
    item_repo = ItemRepository(session)
    source_repo = SourceRepository(session)
    event_repo = EventRepository(session)

    item = item_repo.get(item_id)
    if item is None:
        raise LookupError("Item not found")

    source = source_repo.get(item.source_id)
    snapshots = list(item_repo.list_snapshots(item_id, limit=12))
    events = list(
        event_repo.list_for_admin(
            limit=20,
            item_id=item_id,
            severity=params.severity,
            event_type=params.event_type,
            suppressed=params.suppressed,
            search_query=params.search_query,
        )
    )
    if params.search_query:
        snapshots = [
            snapshot
            for snapshot in snapshots
            if _matches_query(
                params.search_query,
                snapshot.title,
                snapshot.price_amount,
                snapshot.availability_status,
                snapshot.rating,
            )
        ]

    event_stats = {
        "total": len(events),
        "high": len([event for event in events if event.severity == "high"]),
        "suppressed": len([event for event in events if event.is_suppressed]),
        "snapshots": len(snapshots),
    }
    return {
        "item": item,
        "source": source,
        "snapshots": snapshots,
        "events": events,
        "event_stats": event_stats,
    }


def build_monitors_page(session: Session, params: MonitorsPageParams) -> dict[str, Any]:
    monitor_repo = MonitorProfileRepository(session)
    match_repo = MonitorMatchRepository(session)
    delivery_repo = NotificationDeliveryRepository(session)
    run_repo = RunRepository(session)
    source_repo = SourceRepository(session)
    user_repo = TelegramUserRepository(session)
    chat_repo = TelegramChatRepository(session)

    profiles = list(
        monitor_repo.list_for_admin(
            source_id=params.source_id,
            is_active=params.is_active,
            priority_mode=params.priority_mode,
            instant_alerts_enabled=params.instant_alerts_enabled,
            digest_enabled=params.digest_enabled,
            search_query=params.search_query,
        )
    )
    sources = {source.id: source for source in source_repo.list_sources()}
    users = {user.id: user for user in user_repo.list_recent(limit=200)}
    chats = {chat.id: chat for chat in chat_repo.list_recent(limit=200)}

    visible_profile_ids = {profile.id for profile in profiles}
    recent_matches = [
        match
        for match in match_repo.list_recent(limit=120)
        if match.monitor_profile_id in visible_profile_ids
    ]
    recent_deliveries = [
        delivery
        for delivery in delivery_repo.list_recent(limit=120)
        if delivery.monitor_profile_id in visible_profile_ids
    ]
    profile_activity = _build_monitor_activity(profiles, recent_matches, recent_deliveries)
    recent_match_events = {
        match.detected_event_id: session.get(DetectedEvent, match.detected_event_id)
        for match in recent_matches[:8]
        if match.detected_event_id
    }
    recent_match_runs = {
        match.monitoring_run_id: run_repo.get(match.monitoring_run_id)
        for match in recent_matches[:8]
        if match.monitoring_run_id
    }
    activity_stats = {
        "matches_24h": sum(
            int(profile_activity[profile.id]["matches_24h"]) for profile in profiles
        ),
        "deliveries_7d": sum(
            int(profile_activity[profile.id]["deliveries_7d"]) for profile in profiles
        ),
        "instant": len([profile for profile in profiles if profile.instant_alerts_enabled]),
        "digest": len([profile for profile in profiles if profile.digest_enabled]),
        "high_only": len([profile for profile in profiles if profile.priority_mode == "high_only"]),
    }
    monitor_stats = {
        "total": len(profiles),
        "active": len([profile for profile in profiles if profile.is_active]),
        "matches_24h": activity_stats["matches_24h"],
        "deliveries_7d": activity_stats["deliveries_7d"],
    }
    return {
        "profiles": profiles,
        "profiles_by_id": {profile.id: profile for profile in profiles},
        "sources": sources,
        "users": users,
        "chats": chats,
        "monitor_stats": monitor_stats,
        "profile_activity": profile_activity,
        "activity_stats": activity_stats,
        "recent_matches": recent_matches[:8],
        "recent_match_events": recent_match_events,
        "recent_match_runs": recent_match_runs,
        "recent_deliveries": recent_deliveries[:8],
        "monitor_target_label": monitor_target_label,
    }


def build_monitor_detail_page(
    session: Session, *, monitor_id: int, params: MonitorDetailPageParams
) -> dict[str, Any]:
    monitor_repo = MonitorProfileRepository(session)
    match_repo = MonitorMatchRepository(session)
    delivery_repo = NotificationDeliveryRepository(session)
    source_repo = SourceRepository(session)
    run_repo = RunRepository(session)

    profile = monitor_repo.get(monitor_id)
    if profile is None:
        raise LookupError("Monitor profile not found")

    telegram_user = session.get(TelegramUser, profile.telegram_user_id)
    telegram_chat = session.get(TelegramChat, profile.telegram_chat_id)
    source = source_repo.get(profile.source_id)

    all_matches = list(match_repo.list_by_monitor(monitor_id, limit=200))
    all_deliveries = list(delivery_repo.list_by_monitor(monitor_id, limit=200))
    matches = list(all_matches[:40])
    deliveries = list(all_deliveries[:40])

    if params.priority:
        matches = [match for match in matches if match.priority == params.priority]
    if params.delivery_status:
        deliveries = [
            delivery for delivery in deliveries if delivery.status == params.delivery_status
        ]
    if params.delivery_type:
        deliveries = [
            delivery for delivery in deliveries if delivery.delivery_type == params.delivery_type
        ]

    feed_events = {
        match.detected_event_id: session.get(DetectedEvent, match.detected_event_id)
        for match in all_matches[:6]
        if match.detected_event_id
    }
    events = {
        match.detected_event_id: session.get(DetectedEvent, match.detected_event_id)
        for match in matches
        if match.detected_event_id
    }
    events = {**feed_events, **events}
    runs = {
        match.monitoring_run_id: run_repo.get(match.monitoring_run_id)
        for match in matches
        if match.monitoring_run_id
    }
    if params.search_query:
        matches = [
            match
            for match in matches
            if _matches_query(
                params.search_query,
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
                params.search_query,
                delivery.delivery_type,
                delivery.status,
                delivery.message_preview,
                delivery.error_text,
            )
        ]

    activity = _build_monitor_activity([profile], all_matches, all_deliveries)[profile.id]
    last_match = all_matches[0] if all_matches else None
    last_delivery = all_deliveries[0] if all_deliveries else None
    activity_feed = sorted(
        [
            {
                "kind": "match",
                "created_at": match.created_at,
                "title": events.get(match.detected_event_id).summary_text
                if match.detected_event_id in events and events.get(match.detected_event_id)
                else match.match_reason,
                "meta": match.priority,
                "href": f"/admin/runs/{match.monitoring_run_id}"
                if match.monitoring_run_id
                else f"/admin/monitors/{profile.id}",
            }
            for match in all_matches[:6]
        ]
        + [
            {
                "kind": "delivery",
                "created_at": delivery.created_at,
                "title": delivery.message_preview or "Notification delivery logged",
                "meta": delivery.status,
                "href": f"/admin/monitors/{profile.id}?delivery_status={delivery.status}",
            }
            for delivery in all_deliveries[:6]
        ],
        key=lambda item: item["created_at"],
        reverse=True,
    )[:8]
    return {
        "profile": profile,
        "source": source,
        "telegram_user": telegram_user,
        "telegram_chat": telegram_chat,
        "matches": matches,
        "deliveries": deliveries,
        "events": events,
        "runs": runs,
        "activity": activity,
        "last_match": last_match,
        "last_delivery": last_delivery,
        "activity_feed": activity_feed,
        "match_stats": {
            "total": len(all_matches),
            "high": len([match for match in all_matches if match.priority == "high"]),
            "medium": len([match for match in all_matches if match.priority == "medium"]),
            "deliveries": len(all_deliveries),
            "runs": len(
                {match.monitoring_run_id for match in all_matches if match.monitoring_run_id}
            ),
        },
    }


def build_deliveries_page(session: Session, params: DeliveriesPageParams) -> dict[str, Any]:
    delivery_repo = NotificationDeliveryRepository(session)
    monitor_repo = MonitorProfileRepository(session)
    chat_repo = TelegramChatRepository(session)
    source_repo = SourceRepository(session)

    deliveries = list(
        delivery_repo.list_for_admin(
            status=params.status,
            delivery_type=params.delivery_type,
            monitor_profile_id=params.monitor_profile_id,
            telegram_chat_id=params.telegram_chat_id,
            source_id=params.source_id,
            monitoring_run_id=params.monitoring_run_id,
            search_query=params.search_query,
        )
    )
    profiles = {profile.id: profile for profile in monitor_repo.list_recent(limit=200)}
    chats = {chat.id: chat for chat in chat_repo.list_recent(limit=200)}
    sources = {source.id: source for source in source_repo.list_sources()}

    delivery_stats = {
        "total": len(deliveries),
        "sent": len([delivery for delivery in deliveries if delivery.status == "sent"]),
        "failed": len([delivery for delivery in deliveries if delivery.status == "failed"]),
        "suppressed": len([delivery for delivery in deliveries if delivery.status == "suppressed"]),
    }
    return {
        "deliveries": deliveries,
        "profiles": profiles,
        "chats": chats,
        "sources": sources,
        "delivery_stats": delivery_stats,
        "delivery_filters": {
            "profiles": sorted(profiles.values(), key=lambda profile: profile.name.lower()),
            "chats": sorted(
                chats.values(),
                key=lambda chat: (chat.title or str(chat.telegram_chat_id)).lower(),
            ),
            "sources": sorted(sources.values(), key=lambda source: source.name.lower()),
        },
    }


def build_runs_page(session: Session, params: RunsPageParams) -> dict[str, Any]:
    run_repo = RunRepository(session)
    source_repo = SourceRepository(session)

    runs = list(
        run_repo.list_for_admin(
            limit=30,
            status=params.status,
            trigger_type=params.trigger_type,
            source_id=params.source_id,
            search_query=params.search_query,
        )
    )
    all_runs = list(run_repo.list_recent(limit=30))
    sources = {source.id: source for source in source_repo.list_sources()}
    run_stats = {
        "total": len(runs),
        "succeeded": len([run for run in runs if run.status == "succeeded"]),
        "degraded": len([run for run in runs if run.status == "degraded"]),
        "failed": len([run for run in runs if run.status == "failed"]),
    }
    run_quality = {
        "last_run": all_runs[0] if all_runs else None,
        "fastest_run": min(all_runs, key=lambda run: run.duration_ms or float("inf"))
        if all_runs
        else None,
        "noisiest_run": max(all_runs, key=lambda run: run.events_count or 0) if all_runs else None,
        "most_alerts_run": max(all_runs, key=lambda run: run.alerts_sent_count or 0)
        if all_runs
        else None,
    }
    return {
        "runs": runs,
        "sources": sources,
        "run_stats": run_stats,
        "run_quality": run_quality,
    }


def build_run_detail_page(
    session: Session, *, run_id: int, params: RunDetailPageParams
) -> dict[str, Any]:
    run_repo = RunRepository(session)
    source_repo = SourceRepository(session)
    event_repo = EventRepository(session)
    notification_repo = NotificationRepository(session)
    delivery_repo = NotificationDeliveryRepository(session)
    profile_repo = MonitorProfileRepository(session)
    summary_repo = AISummaryRepository(session)

    run = run_repo.get(run_id)
    if run is None:
        raise LookupError("Run not found")

    events = list(
        event_repo.list_for_admin(
            run_id=run_id,
            severity=params.severity,
            event_type=params.event_type,
            suppressed=params.suppressed,
            search_query=params.search_query,
            limit=None,
        )
    )
    notifications = list(notification_repo.list_by_run(run_id))
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

    if params.notification_status:
        notifications = [
            notification
            for notification in notifications
            if notification.status == params.notification_status
        ]
    if params.notification_type:
        notifications = [
            notification
            for notification in notifications
            if notification.notification_type == params.notification_type
        ]
    if params.delivery_status:
        monitor_deliveries = [
            delivery for delivery in monitor_deliveries if delivery.status == params.delivery_status
        ]
    if params.delivery_type:
        monitor_deliveries = [
            delivery
            for delivery in monitor_deliveries
            if delivery.delivery_type == params.delivery_type
        ]

    if params.search_query:
        notifications = [
            notification
            for notification in notifications
            if _matches_query(
                params.search_query,
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
                params.search_query,
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
            params.search_query, summary.summary_text, summary.highlights_json, summary.status
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
    return {
        "run": run,
        "source": source,
        "events": events,
        "notifications": notifications,
        "monitor_deliveries": monitor_deliveries,
        "monitor_deliveries_preview": monitor_deliveries[:3],
        "monitor_profiles": monitor_profiles,
        "delivery_chats": delivery_chats,
        "summary": summary,
        "event_stats": event_stats,
    }


def build_findings_page(session: Session, params: FindingsPageParams) -> dict[str, Any]:
    event_repo = EventRepository(session)
    source_repo = SourceRepository(session)

    events = list(
        event_repo.list_for_admin(
            limit=40 if params.run_id is None else None,
            run_id=params.run_id,
            source_id=params.source_id,
            severity=params.severity,
            event_type=params.event_type,
            suppressed=params.suppressed,
            search_query=params.search_query,
        )
    )
    all_events = list(
        event_repo.list_for_admin(limit=40 if params.run_id is None else None, run_id=params.run_id)
    )
    sources = {source.id: source for source in source_repo.list_sources()}
    finding_stats = {
        "total": len(events),
        "high": len([event for event in events if event.severity == "high"]),
        "medium": len([event for event in events if event.severity == "medium"]),
        "low": len([event for event in events if event.severity == "low"]),
        "suppressed": len([event for event in events if event.is_suppressed]),
    }
    return {
        "events": events,
        "sources": sources,
        "finding_stats": finding_stats,
        "finding_filters": {
            "sources": sorted(sources.values(), key=lambda source: source.name.lower()),
            "event_types": sorted({event.event_type for event in all_events}),
        },
    }


def monitor_target_label(
    profile, chats: dict[int, TelegramChat], users: dict[int, TelegramUser]
) -> str:
    chat = chats.get(profile.telegram_chat_id)
    user = users.get(profile.telegram_user_id)
    if chat and chat.title:
        return chat.title
    if user and user.username:
        return f"@{user.username}"
    return "Private chat"


def _build_monitor_activity(
    profiles,
    matches,
    deliveries,
) -> dict[int, dict[str, object]]:
    now = _utcnow()
    day_cutoff = now - timedelta(hours=24)
    week_cutoff = now - timedelta(days=7)
    activity: dict[int, dict[str, object]] = {
        profile.id: {
            "matches_24h": 0,
            "matches_7d": 0,
            "high_matches_7d": 0,
            "deliveries_24h": 0,
            "deliveries_7d": 0,
            "failed_deliveries_7d": 0,
            "last_match_at": None,
            "last_match_priority": None,
            "last_match_reason": None,
            "last_delivery_at": None,
            "last_delivery_status": None,
            "last_delivery_type": None,
        }
        for profile in profiles
    }

    for match in matches:
        summary = activity.get(match.monitor_profile_id)
        if summary is None:
            continue
        if summary["last_match_at"] is None:
            summary["last_match_at"] = match.created_at
            summary["last_match_priority"] = match.priority
            summary["last_match_reason"] = match.match_reason
        if match.created_at >= day_cutoff:
            summary["matches_24h"] += 1
        if match.created_at >= week_cutoff:
            summary["matches_7d"] += 1
            if match.priority == "high":
                summary["high_matches_7d"] += 1

    for delivery in deliveries:
        summary = activity.get(delivery.monitor_profile_id)
        if summary is None:
            continue
        if summary["last_delivery_at"] is None:
            summary["last_delivery_at"] = delivery.created_at
            summary["last_delivery_status"] = delivery.status
            summary["last_delivery_type"] = delivery.delivery_type
        if delivery.created_at >= day_cutoff:
            summary["deliveries_24h"] += 1
        if delivery.created_at >= week_cutoff:
            summary["deliveries_7d"] += 1
            if delivery.status == "failed":
                summary["failed_deliveries_7d"] += 1

    return activity


def _build_source_activity(
    sources, runs, events
) -> tuple[dict[int, dict[str, object]], list[dict[str, object]]]:
    activity: dict[int, dict[str, object]] = {
        source.id: {
            "last_run": None,
            "last_event": None,
            "events_last_run": 0,
            "recent_findings": 0,
        }
        for source in sources
    }
    feed: list[dict[str, object]] = []

    for run in runs:
        summary = activity.get(run.source_id)
        if summary is None:
            continue
        if summary["last_run"] is None:
            summary["last_run"] = run
            summary["events_last_run"] = run.events_count
            feed.append(
                {
                    "kind": "run",
                    "source_id": run.source_id,
                    "created_at": run.started_at,
                    "title": f"Run #{run.id} finished {run.status}",
                    "meta": run.status,
                    "href": f"/admin/runs/{run.id}",
                }
            )

    for event in events:
        summary = activity.get(event.source_id)
        if summary is None:
            continue
        summary["recent_findings"] += 1
        if summary["last_event"] is None:
            summary["last_event"] = event
            feed.append(
                {
                    "kind": "finding",
                    "source_id": event.source_id,
                    "created_at": event.created_at,
                    "title": event.summary_text,
                    "meta": event.severity,
                    "href": f"/admin/findings?source_id={event.source_id}",
                }
            )

    feed.sort(key=lambda item: item["created_at"], reverse=True)
    return activity, feed[:5]


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


def _utcnow():
    from app.core.time import utcnow

    return utcnow()
