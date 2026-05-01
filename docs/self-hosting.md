# Self-hosting Guide

The easiest way to run Free Games Notifier on your own server is with the pre-built Docker image published on [GitHub Container Registry](https://github.com/JulioMoralesB/free-games-notifier/pkgs/container/free-games-notifier). No build step required.

## Prerequisites

- Docker 20.10+
- Docker Compose v2 (`docker compose`) — Compose v1 (`docker-compose`) also works
- A Discord webhook URL — create one via **Server Settings → Integrations → Webhooks** in your Discord server
- (Optional) PostgreSQL 13+ for database-backed storage; the service falls back to JSON file storage when no DB is configured

## Quick Start

### 1. Get the files

```bash
git clone https://github.com/JulioMoralesB/free-games-notifier.git
cd free-games-notifier
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN
```

The file already includes sensible defaults for `DATA_PATH` (`./data`) and `LOGS_PATH` (`./logs`), which Docker bind-mounts for persistent storage and logs. Change them to absolute paths if you prefer a specific location.

Optionally set `REGION` to your IANA timezone string (e.g. `America/Mexico_City`) — this derives timezone, locale, Steam language, and country in one step. See the [Configuration Reference](configuration.md) for all options.

To enable PostgreSQL, uncomment and fill in the `DB_*` variables; otherwise JSON file storage is used automatically. See [Storage Backends](storage-backends.md) for a comparison.

### 3. Start the service

```bash
docker compose pull   # pull the pre-built image from ghcr.io
docker compose up -d
```

Docker Compose creates the `data/` and `logs/` directories and the internal network on first run. The service applies any pending database migrations and begins the scheduling loop.

The dashboard and REST API are available at `http://localhost:8000`.

> **Building from source:** If you'd rather build the image locally (e.g. for testing local changes), skip `docker compose pull` and run `docker compose up -d --build` instead.

## Database migrations

When `DB_HOST` is configured, Alembic migrations run **automatically on startup** — no manual step is needed. Migration log lines on first boot are expected. For manual migration commands, see [Database Migrations](database-migrations.md).

## Pinning to a specific version

`compose.yaml` uses `:latest` by default. For reproducible deployments, pin to a specific semver tag:

```yaml
# compose.yaml
image: ghcr.io/juliomoralesb/free-games-notifier:1.2.3
```

Available versions are listed on the [packages page](https://github.com/JulioMoralesB/free-games-notifier/pkgs/container/free-games-notifier).

## Updating

```bash
docker compose pull
docker compose up -d
```

This pulls the latest image and restarts the service. Any new migrations run automatically on startup.

## Using only Docker (no Compose)

```bash
docker run -d \
  --name free-games-notifier \
  -e DISCORD_WEBHOOK_URL="YOUR_WEBHOOK_URL" \
  -e REGION=America/New_York \
  -v /your/data/path:/mnt/data \
  -v /your/logs/path:/mnt/logs \
  -p 8000:8000 \
  ghcr.io/juliomoralesb/free-games-notifier:latest
```

## Troubleshooting

See the [Troubleshooting Guide](troubleshooting.md) for common issues and their solutions.
