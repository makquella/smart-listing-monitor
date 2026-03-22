from dataclasses import dataclass, field


@dataclass(slots=True)
class ParsedItem:
    canonical_url: str
    title: str
    price_amount: float | None
    currency: str
    availability_status: str
    rating: str | None
    external_id: str | None = None
    attributes: dict = field(default_factory=dict)


@dataclass(slots=True)
class ParseResult:
    items: list[ParsedItem]
    pages_fetched: int
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedItem:
    source_item_key: str
    canonical_url: str
    title: str
    price_amount: float | None
    currency: str
    availability_status: str
    rating: str | None
    external_id: str | None
    attributes: dict
    comparison_hash: str


@dataclass(slots=True)
class EventDraft:
    source_item_key: str
    item_id: int | None
    event_type: str
    severity: str
    dedupe_key: str
    old_value: dict | None
    new_value: dict | None
    changed_fields: list[str]
    summary_text: str
    is_suppressed: bool = False
    suppressed_reason: str | None = None


@dataclass(slots=True)
class HealthEvaluation:
    status: str
    parse_completeness_ratio: float


@dataclass(slots=True)
class Highlight:
    title: str
    severity: str
    why_it_matters: str


@dataclass(slots=True)
class SummaryResult:
    summary_text: str
    highlights: list[dict]
    status: str
    raw_response: dict


@dataclass(slots=True)
class MonitorProfileCreate:
    telegram_user_external_id: int
    telegram_chat_external_id: int
    chat_type: str
    username: str | None
    first_name: str | None
    last_name: str | None
    chat_title: str | None
    source_id: int
    name: str
    category: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    instant_alerts_enabled: bool = True
    digest_enabled: bool = True
    priority_mode: str = "high_medium"


@dataclass(slots=True)
class MonitorMatchDraft:
    monitor_profile_id: int
    detected_event_id: int
    monitoring_run_id: int
    matched: bool
    match_reason: str
    priority: str
