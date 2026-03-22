from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Parset Monitor"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/app.db"

    request_timeout_seconds: int = 20
    parser_user_agent: str = "ParsetMonitor/1.0 (+https://example.local)"
    parser_detail_fetch_workers: int = Field(default=12, alias="PARSER_DETAIL_FETCH_WORKERS")
    schedule_default_interval_minutes: int = 60
    health_baseline_run_window: int = 5

    removal_miss_threshold: int = Field(default=2, alias="REMOVAL_MISS_THRESHOLD")
    alert_cooldown_hours: int = Field(default=12, alias="ALERT_COOLDOWN_HOURS")
    min_absolute_price_delta: float = Field(default=1.00, alias="MIN_ABSOLUTE_PRICE_DELTA")
    min_percent_price_delta: float = Field(default=2.0, alias="MIN_PERCENT_PRICE_DELTA")
    degraded_parse_ratio_threshold: float = Field(default=0.70, alias="DEGRADED_PARSE_RATIO_THRESHOLD")

    books_source_name: str = "Books to Scrape"
    books_source_slug: str = "books-to-scrape"
    books_source_base_url: str = "https://books.toscrape.com/"
    books_source_start_url: str = "https://books.toscrape.com/catalogue/page-1.html"

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_bot_control_enabled: bool = Field(default=False, alias="TELEGRAM_BOT_CONTROL_ENABLED")
    telegram_bot_polling_timeout_seconds: int = Field(default=30, alias="TELEGRAM_BOT_POLLING_TIMEOUT_SECONDS")

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url.startswith("sqlite:///./"):
            relative = self.database_url.removeprefix("sqlite:///./")
            return f"sqlite:///{(BASE_DIR / relative).resolve()}"
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
