# Parset Monitor

Parset Monitor is a portfolio-ready MVP for intelligent product and listing monitoring. It tracks supported sources, stores item state over time, detects meaningful changes, suppresses noise, sends Telegram alerts, generates Gemini summaries, and exposes run history in a focused FastAPI dashboard.

## What it demonstrates

- Stateful scraping, not just page parsing
- Deterministic change detection for new, removed, price, availability, and attribute changes
- Source health evaluation with `healthy`, `degraded`, and `failing`
- Configurable monitoring rules from `.env`
- Cached attribute hydration so repeat runs avoid unnecessary detail-page fetches
- Telegram integration as both a delivery channel and a bot-based control layer
- Gemini integration for short operator summaries and top highlights
- Run history, findings, monitor profiles, and delivery status in a server-rendered admin UI

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy + SQLite
- APScheduler
- Requests + BeautifulSoup
- Telegram Bot API
- aiogram 3
- Gemini REST API

## Local setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
cp .env.example .env
./.venv/bin/uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/admin`.

If you want the Telegram bot control plane, set `TELEGRAM_BOT_CONTROL_ENABLED=true` before starting the app. Then open your bot in Telegram and send `/start`.

Public demo bot:

- `@fhparserfh_bot` — available when the maintainer demo instance is online

## Configuration

Core monitoring behavior is controlled from `.env`:

- `REMOVAL_MISS_THRESHOLD=2`
- `ALERT_COOLDOWN_HOURS=12`
- `MIN_ABSOLUTE_PRICE_DELTA=1.00`
- `MIN_PERCENT_PRICE_DELTA=2.0`
- `DEGRADED_PARSE_RATIO_THRESHOLD=0.70`
- `PARSER_DETAIL_FETCH_WORKERS=12`

Operational integrations are optional:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_BOT_CONTROL_ENABLED=false`
- `TELEGRAM_BOT_POLLING_TIMEOUT_SECONDS=30`
- `TELEGRAM_MESSAGE_CHUNK_SIZE=3500`
- `TELEGRAM_RETRY_ATTEMPTS=4`
- `TELEGRAM_RETRY_BASE_SECONDS=1.5`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`

If Telegram is not configured, notifications are logged as `skipped`. If Gemini is not configured, the app stores a deterministic fallback summary instead of failing the run.

## MVP behavior

- First successful run seeds the catalogue and creates `new_item` events.
- The first run is the most expensive because it warms category attributes for the source; repeat runs reuse cached attributes and are much faster.
- Repeat runs with no change produce zero new events.
- Removed items are only emitted after the configured number of healthy consecutive misses.
- Degraded runs suppress removals to avoid false positives on suspicious crawls.
- Run locking is intentionally single-process and in-memory for this MVP.
- Supported source parsing is shared at the platform layer. User personalization happens through `MonitorProfile` matching, not per-user re-parsing.

## Telegram-first layer

The monitoring core stays source-centric:

```text
Source -> MonitoringRun -> Item / ItemSnapshot -> DetectedEvent
```

The Telegram-first product layer sits on top:

```text
TelegramUser / TelegramChat -> MonitorProfile -> MonitorMatch -> NotificationDelivery
```

This means:

- a supported source is parsed once per run
- detected events are matched against all active monitor profiles for that source
- instant alerts and digests are delivered per monitor profile and per chat
- the Telegram bot acts as the control plane, while the FastAPI dashboard remains the ops/admin surface

Current bot flows:

- `/start`
- `Create monitor`
- `My monitors`
- `Notifications`
- `Run check`
- `Status`

## Project structure

```text
app/
  api/           FastAPI routes for admin pages and JSON endpoints
  core/          settings, DB, logging, scheduler, time helpers
  models/        SQLAlchemy models
  parsers/       source adapters
  repositories/  DB access layer
  bot/           aiogram control-plane handlers and FSM state
  services/      runner, diffing, health, suppression, Telegram, Gemini, monitor matching
  web/           templates and static assets
tests/           parser, diff, runner, notifier, evaluator, and Gemini tests
```

## Testing

```bash
./.venv/bin/python -m pytest
```

## Notes

- The first source adapter targets `Books to Scrape`, which is safe and stable for portfolio demos.
- The architecture is intentionally ready for additional supported source adapters without introducing arbitrary URL onboarding in v1.
- This MVP is single-process by design, so `SourceRunLockManager` is documented as runtime-only locking rather than a distributed lock system.
