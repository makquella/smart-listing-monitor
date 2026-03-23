from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import Request


def search_query(request: Request) -> str:
    return request.query_params.get("q", "").strip()


def query_value(request: Request, name: str) -> str:
    return request.query_params.get(name, "").strip()


def query_int(request: Request, name: str) -> int | None:
    raw = query_value(request, name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def query_bool(request: Request, name: str) -> bool | None:
    raw = query_value(request, name).lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


@dataclass(slots=True, frozen=True)
class QueryContext:
    search_query: str
    active_filters: list[dict[str, str]]
    persistent_query_params: list[tuple[str, str]]
    search_clear_url: str


def build_query_context(request: Request) -> QueryContext:
    active_filters = [
        {"label": key.replace("_", " ").title(), "value": value}
        for key, value in request.query_params.multi_items()
        if key != "q"
    ]
    persistent_query_params = [
        (key, value) for key, value in request.query_params.multi_items() if key != "q"
    ]
    if persistent_query_params:
        search_clear = f"{request.url.path}?{urlencode(persistent_query_params)}"
    else:
        search_clear = request.url.path
    return QueryContext(
        search_query=search_query(request),
        active_filters=active_filters,
        persistent_query_params=persistent_query_params,
        search_clear_url=search_clear,
    )


@dataclass(slots=True, frozen=True)
class OverviewPageParams:
    search_query: str

    @classmethod
    def from_request(cls, request: Request) -> "OverviewPageParams":
        return cls(search_query=search_query(request))


@dataclass(slots=True, frozen=True)
class SourcesPageParams:
    search_query: str
    health_status: str | None
    is_active: bool | None
    schedule_enabled: bool | None
    attention_only: bool

    @classmethod
    def from_request(cls, request: Request) -> "SourcesPageParams":
        state_filter = query_value(request, "state")
        schedule_filter = query_value(request, "schedule")
        return cls(
            search_query=search_query(request),
            health_status=query_value(request, "health") or None,
            is_active=True
            if state_filter == "active"
            else False
            if state_filter == "paused"
            else None,
            schedule_enabled=(
                True
                if schedule_filter == "enabled"
                else False
                if schedule_filter == "disabled"
                else None
            ),
            attention_only=query_bool(request, "attention") is True,
        )


@dataclass(slots=True, frozen=True)
class SourceDetailPageParams:
    search_query: str
    run_status: str | None
    severity: str | None
    event_type: str | None
    suppressed: bool | None

    @classmethod
    def from_request(cls, request: Request) -> "SourceDetailPageParams":
        return cls(
            search_query=search_query(request),
            run_status=query_value(request, "run_status") or None,
            severity=query_value(request, "severity") or None,
            event_type=query_value(request, "event_type") or None,
            suppressed=query_bool(request, "suppressed"),
        )


@dataclass(slots=True, frozen=True)
class ItemsPageParams:
    search_query: str
    source_id: int | None
    is_active: bool | None
    availability_status: str | None
    rating: str | None

    @classmethod
    def from_request(cls, request: Request) -> "ItemsPageParams":
        state_filter = query_value(request, "state")
        return cls(
            search_query=search_query(request),
            source_id=query_int(request, "source_id"),
            is_active=True
            if state_filter == "active"
            else False
            if state_filter == "removed"
            else None,
            availability_status=query_value(request, "availability") or None,
            rating=query_value(request, "rating") or None,
        )


@dataclass(slots=True, frozen=True)
class ItemDetailPageParams:
    search_query: str
    severity: str | None
    event_type: str | None
    suppressed: bool | None

    @classmethod
    def from_request(cls, request: Request) -> "ItemDetailPageParams":
        return cls(
            search_query=search_query(request),
            severity=query_value(request, "severity") or None,
            event_type=query_value(request, "event_type") or None,
            suppressed=query_bool(request, "suppressed"),
        )


@dataclass(slots=True, frozen=True)
class MonitorsPageParams:
    search_query: str
    source_id: int | None
    is_active: bool | None
    priority_mode: str | None
    instant_alerts_enabled: bool | None
    digest_enabled: bool | None

    @classmethod
    def from_request(cls, request: Request) -> "MonitorsPageParams":
        state_filter = query_value(request, "state")
        return cls(
            search_query=search_query(request),
            source_id=query_int(request, "source_id"),
            is_active=True
            if state_filter == "active"
            else False
            if state_filter == "paused"
            else None,
            priority_mode=query_value(request, "priority_mode") or None,
            instant_alerts_enabled=query_bool(request, "instant"),
            digest_enabled=query_bool(request, "digest"),
        )


@dataclass(slots=True, frozen=True)
class MonitorDetailPageParams:
    search_query: str
    priority: str | None
    delivery_status: str | None
    delivery_type: str | None

    @classmethod
    def from_request(cls, request: Request) -> "MonitorDetailPageParams":
        return cls(
            search_query=search_query(request),
            priority=query_value(request, "priority") or None,
            delivery_status=query_value(request, "delivery_status") or None,
            delivery_type=query_value(request, "delivery_type") or None,
        )


@dataclass(slots=True, frozen=True)
class DeliveriesPageParams:
    search_query: str
    status: str | None
    delivery_type: str | None
    monitor_profile_id: int | None
    telegram_chat_id: int | None
    source_id: int | None
    monitoring_run_id: int | None

    @classmethod
    def from_request(cls, request: Request) -> "DeliveriesPageParams":
        return cls(
            search_query=search_query(request),
            status=query_value(request, "status") or None,
            delivery_type=query_value(request, "delivery_type") or None,
            monitor_profile_id=query_int(request, "monitor_id"),
            telegram_chat_id=query_int(request, "chat_id"),
            source_id=query_int(request, "source_id"),
            monitoring_run_id=query_int(request, "run_id"),
        )


@dataclass(slots=True, frozen=True)
class RunsPageParams:
    search_query: str
    status: str | None
    trigger_type: str | None
    source_id: int | None

    @classmethod
    def from_request(cls, request: Request) -> "RunsPageParams":
        return cls(
            search_query=search_query(request),
            status=query_value(request, "status") or None,
            trigger_type=query_value(request, "trigger") or None,
            source_id=query_int(request, "source_id"),
        )


@dataclass(slots=True, frozen=True)
class RunDetailPageParams:
    search_query: str
    severity: str | None
    event_type: str | None
    suppressed: bool | None
    notification_status: str | None
    notification_type: str | None
    delivery_status: str | None
    delivery_type: str | None

    @classmethod
    def from_request(cls, request: Request) -> "RunDetailPageParams":
        return cls(
            search_query=search_query(request),
            severity=query_value(request, "severity") or None,
            event_type=query_value(request, "event_type") or None,
            suppressed=query_bool(request, "suppressed"),
            notification_status=query_value(request, "notification_status") or None,
            notification_type=query_value(request, "notification_type") or None,
            delivery_status=query_value(request, "delivery_status") or None,
            delivery_type=query_value(request, "delivery_type") or None,
        )


@dataclass(slots=True, frozen=True)
class FindingsPageParams:
    search_query: str
    run_id: int | None
    severity: str | None
    event_type: str | None
    source_id: int | None
    suppressed: bool | None

    @classmethod
    def from_request(cls, request: Request) -> "FindingsPageParams":
        return cls(
            search_query=search_query(request),
            run_id=query_int(request, "run_id"),
            severity=query_value(request, "severity") or None,
            event_type=query_value(request, "event_type") or None,
            source_id=query_int(request, "source_id"),
            suppressed=query_bool(request, "suppressed"),
        )
