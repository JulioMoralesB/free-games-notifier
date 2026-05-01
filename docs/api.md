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
