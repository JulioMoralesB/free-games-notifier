# Cloudflare Mirror (always-on dashboard and `/api/summary`)

If the machine running the notifier isn't on 24/7 (a homelab server that powers on for a daily window, a laptop, …), the dashboard and anything polling [`GET /api/summary`](api.md#dashboard-summary-contract) go dark whenever the host is off.

The Cloudflare mirror fixes that without moving the scraper. A small Cloudflare Worker + D1 database holds a **read-only replica** fed by the notifier, and serves the dashboard, `GET /games/history` and `GET /api/summary` around the clock — same URLs, same contracts. It fits the Workers **Free** plan.

## How it works

```
 notifier host (runs when it's on)                        Cloudflare (always on)
┌──────────────────────────────────┐                     ┌─────────────────────────────────────┐
│ check: scrape → dedupe → Discord │  1. summary         │ POST /api/mirror/summary ─┐         │
│ then push_to_mirror()            │ ──────────────────▶ │ POST /api/mirror/games  ──┴─▶ D1    │
│                                  │  2. history chunks  │                                     │
└──────────────────────────────────┘  Bearer token       │ /dashboard/*   static assets (free) │ ◀── browsers
                                      (fire & forget)    │ GET /games/history   ─▶ D1 (SQL)    │ ◀── the dashboard
                                                         │ GET /api/summary     ─▶ D1          │ ◀── pollers (X-API-Key)
                                                         │ Cron (hourly): stale? ─▶ Discord     │
                                                         └─────────────────────────────────────┘
```

- **Push.** After every *completed* check, the notifier POSTs the exact body of its own `/api/summary`, then syncs the full game history in chunks of 100. Every request is one attempt with a short timeout (`MIRROR_TIMEOUT`, default 5 s), no retries; the first failure stops the push, so a down mirror costs at most one timeout per check. Failures are logged as a `WARNING` (host only — never the URL path, token, or exception text) and nothing else: the push can never fail the check, the heartbeat, or the process. A check that bails out early (nothing scraped, storage down) doesn't push, so `last_check_at` on the mirror stays honest.
- **History sync.** All chunks of one sync share a `sync_id` and only the last is marked `final`. The mirror upserts every chunk, and only a `final` chunk deletes games the sync didn't include — so a sync that fails partway only ever adds or updates, never removes. Each chunk is applied as one D1 batch (a SQL transaction).
- **Serve.** The dashboard's files are static assets: served by Cloudflare directly, free, without running the Worker. `GET /games/history` filters, sorts and paginates in SQL **exactly like the Python endpoint** — a shared fixture (`cloudflare/mirror/test/fixtures/history-parity.json`) is checked against both implementations in CI. Promotion status (`active`/`expired` in the history, and the `/api/summary` list) is computed against the current time **on every request**, so a snapshot that's days old never shows an ended promotion as free. Responses carry an `x-served-by: free-games-mirror` header.
- **Freshness alert.** An hourly Cron Trigger checks `last_check_at`. When it's older than `STALE_AFTER_HOURS` (default 26 h), it posts once to a Discord webhook. The alert fires at most once per stale episode, and the next successful push re-arms it. If Discord is down, it retries on the next hour.

The data on the mirror is as fresh as the last completed check. With routes on your existing hostname, the mirror serves these paths **even while the host is on** — there is a single source for them, not two that could disagree.

### What still needs the host

- `POST /check` and `POST /notify/discord/resend`
- `/games/latest`, `/health`, `/metrics`, `/config` (the dashboard doesn't use them)
- scraping and Discord notifications themselves (they run on the host's schedule; with a daily power-on window, the check that runs at startup covers the day)

## Security model

| Path | Credential | Notes |
|---|---|---|
| `/dashboard/*`, `GET /games/history` | none | Public, exactly like on the notifier. |
| `GET /api/summary` | `X-API-Key` = `DASHBOARD_API_KEY` | Same key as the notifier. Fails closed: an unset secret rejects every request. |
| `POST /api/mirror/summary`, `POST /api/mirror/games` | `Authorization: Bearer` = `INGEST_TOKEN` | The only write paths. The read key can't write. Payloads validated and capped (summary: 256 KB / 500 promotions; history: 1 MB / 200 games per chunk). |

Secret comparisons are constant-time. There is no CORS (same as the Python service). If you put the hostname behind **Cloudflare Access**, add a bypass or service-token policy for the paths above, or both the pollers and the push will be redirected to the Access login.

## Free plan budget

Assumes a few hundred games in the history and one check per day.

| Resource | Usage | Free plan limit |
|---|---|---|
| Static asset requests (dashboard files) | Every page load | Free and unlimited |
| Worker requests | 1 + ⌈games / 100⌉ pushes per check, 1 per dashboard page/filter change, your pollers' reads, 24 cron runs/day | 100,000/day |
| CPU per invocation | Parse ≤ 100 games or serialize one page of 1–100 games; filtering/sorting runs inside D1 | 10 ms |
| Subrequests per invocation | 1 D1 batch (+1 Discord call on a stale alert) | 50 |
| Cron Triggers | 1 (`0 * * * *`) | 5 per account |
| D1 rows written | ≈ games + 1 per check (e.g. 600/day; ~14,400/day with hourly checks) | 100,000/day |
| D1 rows read | ≈ 2 × games per history request (count + page) | 5,000,000/day |
| D1 storage | ~1–2 KB per game | 500 MB |

Exceeding the CPU limit doesn't cost money on the Free plan: that one invocation fails with error 1102 and the next push or page load works normally.

Sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Workers & D1 pricing](https://developers.cloudflare.com/workers/platform/pricing/), [D1 limits](https://developers.cloudflare.com/d1/platform/limits/), [static assets billing](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/), [D1 batch transactions](https://developers.cloudflare.com/d1/worker-api/d1-database/).

## Setup

You need a Cloudflare account and Node.js 20+ (to build the dashboard). To keep the URLs you already use, the notifier's hostname must be on a Cloudflare zone and proxied (orange cloud — a Cloudflare Tunnel hostname already is). The Worker then takes over **only** the paths listed in `routes`; every other path keeps reaching your host.

All commands run from `cloudflare/mirror/` and use `npx wrangler@4` (run `npx wrangler@4 login` once).

1. **Generate the ingest token** (keep it for steps 4 and 6):
   ```bash
   openssl rand -hex 32
   ```
2. **Create the D1 database** and note the `database_id` it prints:
   ```bash
   npx wrangler@4 d1 create free-games-mirror
   ```
3. **Create your config** from the template and fill in the `REPLACE_ME_*` values (hostname, zone, `database_id`). `wrangler.jsonc` is gitignored.
   ```bash
   cp wrangler.example.jsonc wrangler.jsonc
   ```
4. **Install, apply the schema and set the secrets** (each `secret put` prompts for the value):
   ```bash
   npm install
   npx wrangler@4 d1 migrations apply free-games-mirror --remote
   npx wrangler@4 secret put DASHBOARD_API_KEY    # same value as the notifier's DASHBOARD_API_KEY
   npx wrangler@4 secret put INGEST_TOKEN         # the token from step 1
   npx wrangler@4 secret put DISCORD_WEBHOOK_URL  # optional: where freshness alerts go
   ```
5. **Deploy.** This builds the dashboard from `../../dashboard` into `public/` first (the `build` hook in `wrangler.jsonc`):
   ```bash
   npx wrangler@4 deploy
   ```
6. **Point the notifier at it** — add to the notifier's `.env` (never inline in `compose.yaml`) and recreate the container:
   ```bash
   MIRROR_URL=https://free-games.example.com
   MIRROR_TOKEN=<the token from step 1>
   ```
   ```bash
   docker compose up -d
   ```
   The container runs a check at startup, which fills the mirror.
7. **Verify.** The notifier's log should show `Pushed summary (…) to mirror at free-games.example.com` and `Synced N game(s) to mirror …`, and both of these should print `x-served-by: free-games-mirror`:
   ```bash
   curl -si "https://free-games.example.com/games/history?limit=1" | grep -i x-served-by
   ```
   ```bash
   curl -si -H "X-API-Key: $DASHBOARD_API_KEY" https://free-games.example.com/api/summary | grep -i x-served-by
   ```

**Updating:** after pulling a new version, re-run `npx wrangler@4 d1 migrations apply free-games-mirror --remote` and `npx wrangler@4 deploy` from `cloudflare/mirror/`, so the mirror ships the same dashboard as the notifier.

### Where each value lives

| Value | Notifier `.env` | Worker | How to get it |
|---|---|---|---|
| Ingest token | `MIRROR_TOKEN` | secret `INGEST_TOKEN` | `openssl rand -hex 32` — **must match** on both sides |
| Mirror base URL | `MIRROR_URL` | — | `https://<your hostname>` (no path) |
| Read key | `DASHBOARD_API_KEY` (unchanged) | secret `DASHBOARD_API_KEY` | Your existing key — **must match** so pollers keep working |
| Alert webhook | — | secret `DISCORD_WEBHOOK_URL` (optional) | Discord → channel settings → Integrations → Webhooks |
| Staleness threshold | — | var `STALE_AFTER_HOURS` in `wrangler.jsonc` | Default `26` |
| D1 database id | — | `database_id` in `wrangler.jsonc` | Printed by `wrangler d1 create` |
| Hostname / zone | — | `routes` in `wrangler.jsonc` | Your existing notifier hostname |

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Notifier logs `Mirror at … rejected the summary: HTTP 401` | `MIRROR_TOKEN` ≠ Worker `INGEST_TOKEN`. |
| Notifier logs `HTTP 400` | Payload failed validation; the Worker log (`npx wrangler@4 tail`) has the reason. |
| Notifier logs `Mirror skipped N invalid game record(s)` | Some history records didn't match the GameItem shape; they're left out of the mirror. |
| Responses have no `x-served-by` header | The route isn't matching: check the patterns/zone in `wrangler.jsonc` and that the hostname is proxied. |
| Dashboard loads but shows no games | No history sync has completed yet — check the notifier's log after its next check. |
| Pollers get `401` only from the mirror | The Worker's `DASHBOARD_API_KEY` secret differs from the notifier's. |
| Freshness alert every day | The host's checks aren't completing (see its logs), or `STALE_AFTER_HOURS` is shorter than the gap between power-on windows. |

## Development

```bash
cd cloudflare/mirror
npm install
npm run typecheck
npm test   # Node 22+: runs the real D1 SQL against the built-in node:sqlite
```

If you change `GET /games/history` in the Python API on purpose, regenerate the parity fixture with `python -m tests.test_mirror_parity` and update the Worker until `npm test` passes again.
