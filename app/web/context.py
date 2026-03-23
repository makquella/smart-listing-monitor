from fastapi import Request

from app.core.config import get_settings
from app.core.time import format_utc, format_utc_short, utcnow
from app.web.params import build_query_context


def app_settings(request: Request):
    return getattr(request.app.state, "settings", get_settings())


def format_money(price: float | None, currency: str | None = None) -> str:
    if price is None:
        return "n/a"
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{price:.2f}"


def build_base_context(request: Request) -> dict:
    settings = app_settings(request)
    query_context = build_query_context(request)
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
        "fmt_price": format_money,
        "fmt_dt": format_utc,
        "fmt_dt_short": format_utc_short,
        "fmt_duration": lambda ms: f"{((ms or 0) / 1000):.1f}s",
        "fmt_ratio": lambda value: "n/a" if value is None else f"{value:.2f}",
        "search_query": query_context.search_query,
        "active_filters": query_context.active_filters,
        "persistent_query_params": query_context.persistent_query_params,
        "search_clear_url": query_context.search_clear_url,
    }
