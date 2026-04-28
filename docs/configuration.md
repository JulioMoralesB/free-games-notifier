# Configuration Reference

All configuration is driven by environment variables. For Docker deployments, set them in a `.env` file at the repo root (copy from [`.env.example`](../.env.example) to start).

## Required

| Variable | Description |
|----------|-------------|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL for sending notifications. Create one via **Server Settings → Integrations → Webhooks**. |

## Region & Localization

The `REGION` variable is the recommended way to localize the service — set one IANA timezone string and the rest is derived automatically.

| Variable | Default | Description |
|----------|---------|-------------|
| `REGION` | _(empty)_ | **Recommended.** IANA timezone string (e.g. `America/Mexico_City`). Derives `TIMEZONE`, `LOCALE`, `EPIC_GAMES_REGION`, `STEAM_LANGUAGE`, and `STEAM_COUNTRY`. Individual variables below take precedence when also set. Supported values are listed in [`.env.example`](../.env.example). |
| `TIMEZONE` | `UTC` | IANA timezone for date display in notifications (e.g. `America/New_York`, `Europe/London`). |
| `LOCALE` | `en_US.UTF-8` | Locale for date formatting (e.g. `es_MX.UTF-8`, `de_DE.UTF-8`). All locales supported by the built-in region profiles are pre-installed in the Docker image. |
| `EPIC_GAMES_REGION` | `en-US` | Region code used in Epic Games Store links (e.g. `es-MX`, `de-DE`). |
| `STEAM_LANGUAGE` | `english` | Language for Steam game descriptions (e.g. `spanish`, `french`). Full list: [Steam localization languages](https://partner.steamgames.com/doc/store/localization/languages). |
| `STEAM_COUNTRY` | `US` | ISO 3166-1 alpha-2 country code for Steam store requests — controls price currency (e.g. `MX` → MXN, `DE` → EUR, `GB` → GBP). |

## Stores

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLED_STORES` | `epic` | Comma-separated list of stores to scrape. Supported: `epic`, `steam` (e.g. `epic,steam`). |
| `EPIC_GAMES_API_URL` | Official API | Override for the Epic Games Store API endpoint. |
| `STEAM_REQUEST_DELAY_MS` | `1500` | Milliseconds to wait between Steam HTTP requests to avoid rate limiting. |

## Database (Optional)

Leave all `DB_*` variables empty to use JSON file storage. See [Storage Backends](storage-backends.md) for a comparison.

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | _(empty)_ | PostgreSQL host. Empty = file storage. |
| `DB_PORT` | `5432` | PostgreSQL port. |
| `DB_NAME` | _(empty)_ | PostgreSQL database name. |
| `DB_USER` | _(empty)_ | PostgreSQL username. |
| `DB_PASSWORD` | _(empty)_ | PostgreSQL password. |

## Scheduler

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL_HOURS` | _(empty)_ | Run on a repeating interval (e.g. `6` = every 6 hours). Minimum: `1`. Recommended when Steam is enabled. Leave empty to use `SCHEDULE_TIME`. |
| `SCHEDULE_TIME` | `12:00` | Daily check time in `HH:MM`, interpreted in `TIMEZONE`. Used only when `CHECK_INTERVAL_HOURS` is not set. |

## Health Check Monitoring

Optional integration with [Healthchecks.io](https://healthchecks.io/) or [UptimeKuma](https://github.com/louislam/uptime-kuma) for service monitoring.

| Variable | Default | Description |
|----------|---------|-------------|
| `HEALTHCHECK_URL` | _(empty)_ | Healthchecks.io or UptimeKuma ping URL. |
| `ENABLE_HEALTHCHECK` | `false` | Enable health check pings. Only activate after setting `HEALTHCHECK_URL`. |
| `HEALTHCHECK_INTERVAL` | `1` | Health check ping interval in minutes. |

## REST API

See the [API Reference](api.md) for endpoint documentation.

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `0.0.0.0` | Interface the REST API and dashboard server binds to. |
| `API_PORT` | `8000` | Port the REST API and dashboard server listens on. |
| `API_KEY` | _(empty)_ | Secret key for protecting mutating API endpoints and `GET /config`. Leave empty to disable auth. |

## Notifications

| Variable | Default | Description |
|----------|---------|-------------|
| `DATE_FORMAT` | `%B %d, %Y at %I:%M %p` | strftime format for the promotion end date in Discord notifications. |

## Docker bind mounts

Used by `compose.yaml` to persist data and logs on the host.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_PATH` | `./data` | Host directory bind-mounted to `/mnt/data` in the container. |
| `LOGS_PATH` | `./logs` | Host directory bind-mounted to `/mnt/logs` in the container. |

## Steam-specific notes

- **Free promotions on Steam are infrequent.** When only Steam is enabled (or when Steam returns no results), the scheduler logs *"No free games found"* more often than with Epic — this is expected.
- **Rate limiting:** Steam requests are throttled by `STEAM_REQUEST_DELAY_MS` (default 1500 ms) to avoid HTTP 429 errors. Lowering the delay can trigger rate limits; raising it is safe.
- **Use `CHECK_INTERVAL_HOURS` with Steam.** Steam free games can appear at any time of day, unlike the predictable Epic Thursday rotation.
