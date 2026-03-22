from datetime import datetime, timezone


UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def format_utc(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    return ensure_utc(value).strftime("%b %d, %Y %H:%M UTC")


def format_utc_short(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    return ensure_utc(value).strftime("%b %d, %H:%M")
