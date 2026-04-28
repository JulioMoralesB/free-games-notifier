# Architecture

A high-level overview of how the project is structured and how data flows through it.

## Project layout

```
.
├── main.py                       # Scheduler entry point + API server thread
├── api.py                        # FastAPI REST API + dashboard static mount
├── config.py                     # Environment variables + region profiles
├── requirements.txt              # Python runtime dependencies
├── requirements-dev.txt          # Test + lint dependencies
├── alembic.ini                   # Alembic migration tool configuration
├── alembic/versions/             # Versioned schema migration scripts
├── compose.yaml                  # Docker Compose orchestration
├── Dockerfile                    # Multi-stage image (Node builder → Python runtime)
├── ruff.toml                     # Linter configuration
│
├── dashboard/                    # React + TypeScript SPA (Vite)
│   └── src/
│       ├── App.tsx               # Top-level state, filters, fetch loop
│       ├── components/           # GameCard, LanguageSelector, Pagination, …
│       └── i18n/                 # Translation strings (en, es)
│
├── modules/
│   ├── models.py                 # FreeGame dataclass shared across modules
│   ├── notifier.py               # Discord webhook sender + embed builder
│   ├── storage.py                # Storage dispatcher (PostgreSQL or JSON file)
│   ├── database.py               # PostgreSQL operations
│   ├── healthcheck.py            # External health check pings
│   ├── retry.py                  # Generic exponential-backoff helper
│   ├── logging_config.py         # JSON structured logging setup
│   └── scrapers/
│       ├── base.py               # Scraper interface
│       ├── epic.py               # Epic Games Store scraper
│       ├── steam.py              # Steam Store scraper
│       └── review_sources.py     # Steam reviews + Metacritic enrichment
│
├── tests/                        # pytest suite
│   ├── conftest.py               # Shared fixtures
│   ├── e2e/                      # Production smoke tests (marker: production)
│   └── test_*.py                 # Unit + integration tests
│
└── docs/                         # Documentation (you are here)
```

## Data flow

```
┌──────────────┐
│  Scheduler   │ — runs every CHECK_INTERVAL_HOURS or daily at SCHEDULE_TIME
│  (main.py)   │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│  Scrapers (modules/scrapers) │
│  - epic.py: GraphQL API      │
│  - steam.py: HTML + JSON     │
└──────┬───────────────────────┘
       │  list[FreeGame]
       ▼
┌──────────────┐    diff vs ┌──────────────┐
│  Deduper     │ ◀────────  │  Storage     │
│  (main.py)   │            │  (storage.py)│
└──────┬───────┘            └──────────────┘
       │  new games
       ▼
┌──────────────┐
│  Notifier    │ — Discord webhook with rich embed
│ (notifier.py)│
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Storage     │ — upsert all current games (preserves still-active across runs)
└──────────────┘
```

The REST API runs on a daemon thread alongside the scheduler, exposing the same storage backend for read access.

## Key design choices

### Single FreeGame model

Every scraper returns `list[FreeGame]` from `modules/models.py`. Adding a new store means implementing `Scraper.fetch_free_games() -> list[FreeGame]` — the rest of the pipeline is store-agnostic.

### Pluggable storage

`modules/storage.py` is a dispatcher: it picks PostgreSQL when `DB_HOST` is set, JSON file otherwise. Both backends implement the same `load_previous_games`, `save_games`, `load_last_notification`, `save_last_notification` interface, so the rest of the codebase doesn't care which is in use.

### Deduplication strategy

The notifier runs daily/hourly but should never send the same notification twice. `main._find_new_games` uses three independent checks:

1. **Active URL set** — URLs whose promo end date is still in the future are suppressed
2. **Recently expired URLs** — a 24-hour grace window after expiry suppresses re-notification when a store returns a wrong end date (e.g. Steam off-by-one-year)
3. **(URL, end_date) seen set** — exact match on the URL + end_date pair from any past run

A game must pass all three to be considered new.

### Adding a new scraper

1. Create `modules/scrapers/yourstore.py` with a class that subclasses `Scraper` (in `base.py`)
2. Implement `store_name` and `fetch_free_games() -> list[FreeGame]`
3. Register it in `modules/scrapers/__init__.py` so `get_enabled_scrapers(["yourstore"])` returns it
4. Add an entry to the `ENABLED_STORES` validation list in `config.py`
5. Update [`docs/configuration.md`](configuration.md) and [`README.md`](../README.md)

### Adding a new dashboard language

See the [Dashboard Developer Guide](dashboard.md#adding-a-new-language).
