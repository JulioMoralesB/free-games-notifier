# REST API Reference

The service exposes a FastAPI REST API on `API_HOST:API_PORT` (default `0.0.0.0:8000`).

**Interactive docs:** Open `http://<host>:<API_PORT>/docs` for the auto-generated Swagger UI with full schema details and a live request console.

## Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | `GET` | — | Epic Games API and database connectivity check |
| `/games/latest` | `GET` | — | Most recently fetched free games |
| `/games/history` | `GET` | — | Paginated full game history |
| `/notify/discord/resend` | `POST` | API key | Re-send the last Discord notification |
| `/metrics` | `GET` | — | Uptime, games processed, notification counts, error counts |
| `/config` | `GET` | API key | Non-secret runtime configuration |
| `/check` | `POST` | API key | Full end-to-end pipeline test (fetch + notify) |
| `/api/summary` | `GET` | Dashboard key | External summary contract for other services (see below) |
| `/dashboard/` | `GET` | — | Web dashboard (served when `dashboard/dist` build artifacts are present) |

## Authentication

Endpoints marked **API key** require an `X-API-Key` header when the `API_KEY` environment variable is set. If `API_KEY` is left empty (the default), authentication is disabled and all endpoints are open — useful for local development but **not recommended in production**.

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/config
```

## Query parameters: `/games/history`

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int (1-100) | `20` | Max games to return per page |
| `offset` | int (≥0) | `0` | Number of games to skip |
| `sort_by` | `end_date` \| `title` | `end_date` | Field to sort by |
| `sort_dir` | `asc` \| `desc` | `desc` | Sort direction |
| `store` | `all` \| `epic` \| `steam` | `all` | Filter by store |
| `status` | `all` \| `active` \| `expired` | `all` | Filter by promotion status |

Filtering and sorting are applied to the full dataset **before** pagination, so counts and ordering are consistent across pages.

## Example: pagination

```bash
# First page
curl http://localhost:8000/games/history?limit=10&offset=0

# Next page
curl http://localhost:8000/games/history?limit=10&offset=10

# Currently free Epic games only
curl "http://localhost:8000/games/history?store=epic&status=active"
```

## Example: end-to-end check

The `/check` endpoint is useful for verifying the full pipeline (scraper → storage check → Discord notification) without affecting stored data:

```bash
curl -X POST -H "X-API-Key: $API_KEY" http://localhost:8000/check
```

You can override the Discord webhook URL for a single request — handy for testing in a separate channel:

```bash
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url":"https://discord.com/api/webhooks/.../..."}' \
  http://localhost:8000/check
```

## Dashboard summary contract

`GET /api/summary` is, unlike the rest of this document, a **versioned external contract**, not an internal API free to evolve. It exists so another service (e.g. a homelab dashboard) can poll one small, stable endpoint instead of reading this service's database or log stream directly. The response shape only ever grows — a breaking change gets a new path, never a modified field.

**Authentication is mandatory**, with no fallback: set `DASHBOARD_API_KEY` and send it as `X-API-Key`. This is a separate secret from `API_KEY` — share it only with the poller. If `DASHBOARD_API_KEY` is unset, every request is rejected (this differs from every other API-key-protected endpoint in this doc, which allow open access when `API_KEY` is left empty).

```bash
curl -H "X-API-Key: $DASHBOARD_API_KEY" http://localhost:8000/api/summary
```

```json
{
  "service": "free-games-notifier",
  "games_tracked": 42,
  "active_promotions": 3,
  "last_check_at": "2026-09-03T12:00:00+00:00"
}
```

| Field | Type | Description |
|---|---|---|
| `service` | string | Always `"free-games-notifier"` — identifies the source when a poller tracks several services |
| `games_tracked` | int | Total games currently in storage |
| `active_promotions` | int | Of those, how many have not yet expired |
| `last_check_at` | string \| null | ISO-8601 UTC timestamp of the last scheduled check that ran to completion; `null` until the first one finishes after startup |

Read-only and side-effect-free — a plain `GET` over already-loaded state, safe to poll frequently. If the storage backend can't be read, the endpoint returns `503` rather than a misleading `games_tracked: 0`; a poller should treat that the same as any other network failure, not as "zero games".
