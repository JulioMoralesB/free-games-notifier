# Summary Mirror (always-on `/api/summary`)

If the machine running the notifier isn't on 24/7 (a homelab server that powers on for a daily window, a laptop, …), anything polling [`GET /api/summary`](api.md#dashboard-summary-contract) — a Home Assistant sensor, a dashboard app — goes dark whenever the host is off.

The summary mirror fixes that without moving the scraper: a tiny Cloudflare Worker + D1 database keeps the latest snapshot and serves the **same contract** (same path, same `X-API-Key`, same fields) around the clock. It fits the Workers **Free** plan.

## How it works

```
 notifier host (runs when it's on)                     Cloudflare (always on)
┌──────────────────────────────────┐   POST snapshot   ┌───────────────────────────────┐
│ check: scrape → dedupe → Discord │ ────────────────▶ │ Worker  /api/summary/snapshot │
│ then push_summary_snapshot()     │   Bearer token    │   └─ D1: latest snapshot      │
└──────────────────────────────────┘   (fire & forget) │                               │
                                                       │ Worker  GET /api/summary      │ ◀── pollers (X-API-Key)
                                                       │   └─ drops expired promos     │
                                                       │ Cron (hourly): stale? → Discord│
                                                       └───────────────────────────────┘
```

- **Push.** After every *completed* check, the notifier POSTs the exact body its own `/api/summary` would return. One attempt, short timeout (`SUMMARY_MIRROR_TIMEOUT`, default 5 s), no retries. Any failure — mirror down, timeout, non-2xx — is logged as a `WARNING` and nothing else: it can never fail the check, the heartbeat, or the process. The next completed check pushes again. A check that bails out early (nothing scraped, storage down) doesn't push, so `last_check_at` on the mirror stays honest.
- **Serve.** The Worker re-applies the "still free" filter (`end_date >= now`, same rule as the Python service) on **every request**, so a snapshot that's days old never lists a promotion that has already ended. Before the first push it returns an empty list with `last_check_at: null`; if D1 can't be read it returns `503`, never a fabricated empty list. Responses carry an `x-summary-source: cloudflare-mirror` header so you can tell which side answered.
- **Freshness alert.** An hourly Cron Trigger checks `last_check_at`. When it's older than `STALE_AFTER_HOURS` (default 26 h), it posts once to a Discord webhook. The alert fires at most once per stale episode, and the next successful push re-arms it. If Discord is down, it retries on the next hour.

### What the mirror does *not* do

Only `/api/summary` is mirrored. These still need the notifier host to be on:

- the dashboard (`/dashboard/`) and `/games/latest`, `/games/history`
- `POST /check` and `POST /notify/discord/resend`
- `/health`, `/metrics`, `/config`
- scraping and Discord notifications themselves (they run on the host's schedule; with a daily power-on window, the check that runs at startup covers the day)

## Security model

| Endpoint | Credential | Notes |
|---|---|---|
| `GET /api/summary` | `X-API-Key` = `DASHBOARD_API_KEY` | Same key as the notifier. Fails closed: an unset secret rejects every request. |
| `POST /api/summary/snapshot` | `Authorization: Bearer` = `INGEST_TOKEN` | The only write path. The read key can't write. Payload validated and capped at 256 KB / 500 promotions. |

Both comparisons are constant-time. There is no CORS (same as the Python service). If you put the hostname behind **Cloudflare Access**, add a bypass or service-token policy for `/api/summary*`, or both the pollers and the push will be redirected to the Access login.

## Free plan budget

| Resource | Usage | Free plan limit |
|---|---|---|
| Worker requests | 1 push per check + your pollers' reads (e.g. every 5 min ≈ 290/day) + 24 cron runs/day | 100,000/day |
| CPU per invocation | Parse/serialize a small JSON document | 10 ms |
| Subrequests per invocation | 1 D1 query (+1 Discord call on a stale alert) | 50 |
| Cron Triggers | 1 (`0 * * * *`) | 5 per account |
| D1 | 1 row; ~1 write per check, 1 read per request | 5M rows read/day, 100k rows written/day, 500 MB |

Sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Workers & D1 pricing](https://developers.cloudflare.com/workers/platform/pricing/), [D1 limits](https://developers.cloudflare.com/d1/platform/limits/).

## Setup

You need a Cloudflare account. To keep the same URL your pollers already use, the notifier's hostname must be on a Cloudflare zone and proxied (orange cloud — a Cloudflare Tunnel hostname already is). The Worker then takes over **only** `/api/summary*` on that hostname; every other path keeps reaching your host.

All commands run from `cloudflare/summary-mirror/` and use `npx wrangler@4` (run `npx wrangler@4 login` once).

1. **Generate the ingest token** (keep it for steps 4 and 6):
   ```bash
   openssl rand -hex 32
   ```
2. **Create the D1 database** and note the `database_id` it prints:
   ```bash
   npx wrangler@4 d1 create free-games-summary
   ```
3. **Create your config** from the template and fill in the `REPLACE_ME_*` values (hostname, zone, `database_id`). `wrangler.jsonc` is gitignored.
   ```bash
   cp wrangler.example.jsonc wrangler.jsonc
   ```
4. **Apply the schema and set the secrets** (each `secret put` prompts for the value):
   ```bash
   npx wrangler@4 d1 migrations apply free-games-summary --remote
   npx wrangler@4 secret put DASHBOARD_API_KEY    # same value as the notifier's DASHBOARD_API_KEY
   npx wrangler@4 secret put INGEST_TOKEN         # the token from step 1
   npx wrangler@4 secret put DISCORD_WEBHOOK_URL  # optional: where freshness alerts go
   ```
5. **Deploy**:
   ```bash
   npx wrangler@4 deploy
   ```
6. **Point the notifier at it** — add to the notifier's `.env` (never inline in `compose.yaml`) and recreate the container:
   ```bash
   SUMMARY_MIRROR_URL=https://free-games.example.com/api/summary/snapshot
   SUMMARY_MIRROR_TOKEN=<the token from step 1>
   ```
   ```bash
   docker compose up -d
   ```
7. **Verify.** The notifier's log should show `Pushed summary snapshot (N active promotion(s)) to free-games.example.com` after its next check, and:
   ```bash
   curl -si -H "X-API-Key: $DASHBOARD_API_KEY" https://free-games.example.com/api/summary | grep -i x-summary-source
   ```
   should print `x-summary-source: cloudflare-mirror`.

### Where each value lives

| Value | Notifier `.env` | Worker | How to get it |
|---|---|---|---|
| Ingest token | `SUMMARY_MIRROR_TOKEN` | secret `INGEST_TOKEN` | `openssl rand -hex 32` — **must match** on both sides |
| Ingest URL | `SUMMARY_MIRROR_URL` | — | `https://<your hostname>/api/summary/snapshot` |
| Read key | `DASHBOARD_API_KEY` (unchanged) | secret `DASHBOARD_API_KEY` | Your existing key — **must match** so pollers keep working |
| Alert webhook | — | secret `DISCORD_WEBHOOK_URL` (optional) | Discord → channel settings → Integrations → Webhooks |
| Staleness threshold | — | var `STALE_AFTER_HOURS` in `wrangler.jsonc` | Default `26` |
| D1 database id | — | `database_id` in `wrangler.jsonc` | Printed by `wrangler d1 create` |
| Hostname / zone | — | `routes` in `wrangler.jsonc` | Your existing notifier hostname |

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Notifier logs `Summary mirror at … rejected the snapshot: HTTP 401` | `SUMMARY_MIRROR_TOKEN` ≠ Worker `INGEST_TOKEN`. |
| Notifier logs `HTTP 400` | Payload failed validation; the Worker log (`wrangler tail`) has the reason. |
| `GET /api/summary` has no `x-summary-source` header | The route isn't matching: check the pattern/zone in `wrangler.jsonc` and that the hostname is proxied. |
| Pollers get `401` only from the mirror | The Worker's `DASHBOARD_API_KEY` secret differs from the notifier's. |
| Freshness alert every day | The host's checks aren't completing (see its logs), or `STALE_AFTER_HOURS` is shorter than the gap between power-on windows. |

## Development

```bash
cd cloudflare/summary-mirror
npm install
npm run typecheck
npm test   # Node 22+: runs the real D1 SQL against the built-in node:sqlite
```
