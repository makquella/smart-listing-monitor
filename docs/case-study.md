# Parset Monitor Case Study

## Summary

Parset Monitor is a Telegram-first monitoring MVP for products and listings. It parses curated supported sources, stores item state over time, detects meaningful changes, suppresses noisy events, generates Gemini summaries, and delivers relevant findings back to Telegram while exposing full run observability in a FastAPI admin dashboard.

## Problem

Most scraping demos prove that HTML can be fetched. They do not prove that the data can be monitored reliably over time.

The practical problem this project solves is:

- a source changes over time
- operators care about meaningful deltas, not raw HTML
- repeated checks need history, identity, health, and delivery
- users want filtered alerts, not a firehose

## Product Framing

This project is intentionally framed as a monitoring platform, not as a “universal scraper.”

Key framing decisions:

- curated adapters instead of arbitrary URL onboarding
- shared parsing at the platform layer
- personalization through `MonitorProfile` matching
- deterministic event generation before AI
- Telegram as control plane plus delivery plane
- admin dashboard as ops surface

## Core Flow

```text
Source
  -> MonitoringRun
  -> Item / ItemSnapshot
  -> DetectedEvent
  -> MonitorProfile matching
  -> Telegram delivery
  -> Dashboard / observability
```

## Technical Highlights

- FastAPI backend with server-rendered operator dashboard
- SQLite + SQLAlchemy + Alembic for MVP persistence
- adapter-based parser layer with multiple supported sources
- stable item identity and snapshot history
- deterministic change detection for new, removed, price, availability, and attribute events
- severity scoring and cooldown-based suppression
- Gemini summaries as an explainability layer on top of deterministic findings
- aiogram-based Telegram bot for monitor control and delivery
- CI, linting, formatting, offline parser fixtures, and smoke tests

## What Makes It Strong For Portfolio

- It demonstrates product thinking, not just code execution.
- It combines scraping, data modeling, notification delivery, AI integration, and operator UX.
- It documents limitations honestly, especially the single-process runtime.
- It shows extensibility with multiple curated adapters instead of pretending to support any site.

## Tradeoffs

This MVP does not try to solve everything:

- no arbitrary source onboarding
- no multi-tenant auth/billing layer
- no distributed workers yet
- no multi-host locking

Those are conscious scope decisions, not missing basics.

## Results Worth Calling Out

- first cold run can parse a large seeded catalog and create structured events
- warm runs reuse cached attributes and become much faster
- Telegram profiles receive filtered alerts instead of raw source-wide noise
- AI summaries stay useful without replacing deterministic monitoring logic

## Next Evolution

The most natural next steps are:

1. more curated adapters
2. worker-backed execution instead of in-process dispatching
3. richer digests and delivery views
4. production deployment beyond the single-process demo runtime
