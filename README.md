# Free Games Notifier

A Python-based scheduler that monitors the Epic Games Store and Steam for free game promotions and sends Discord notifications. Ships as a Docker image with optional PostgreSQL storage, a REST API, and a built-in web dashboard.

![Web Dashboard](https://github.com/user-attachments/assets/1ffef230-45e2-4ef1-9ffb-6a7a9d573d62)

## Features

- 🎮 **Multi-store monitoring** — Epic Games Store and Steam, on a daily schedule or every N hours
- 💬 **Rich Discord notifications** — embeds with title, description, original price, review scores, and DLC indicator
- 📊 **Web dashboard** — browse, filter, and search the full free-games history at `/dashboard/`
- 🔌 **REST API** — health, history, metrics, and notification management endpoints
- 🌍 **Region-aware** — one `REGION` variable derives timezone, locale, Steam language, and country
- 📦 **Pluggable storage** — PostgreSQL when `DB_HOST` is set, JSON file otherwise
- 🐳 **Docker-first** — pre-built multi-arch image on `ghcr.io`

## Quick Start

```bash
git clone https://github.com/JulioMoralesB/free-games-notifier.git
cd free-games-notifier
cp .env.example .env
# Edit .env and set DISCORD_WEBHOOK_URL (minimum required)
docker compose pull
docker compose up -d
```

Dashboard and API are available at `http://localhost:8000`.

For a step-by-step walkthrough, optional PostgreSQL setup, version pinning, and update instructions, see the [Self-hosting Guide](docs/self-hosting.md).

## Documentation

| Topic | Doc |
|---|---|
| Self-hosting with Docker | [docs/self-hosting.md](docs/self-hosting.md) |
| All environment variables | [docs/configuration.md](docs/configuration.md) |
| REST API reference | [docs/api.md](docs/api.md) |
| Storage backends (PostgreSQL vs JSON) | [docs/storage-backends.md](docs/storage-backends.md) |
| Database migrations | [docs/database-migrations.md](docs/database-migrations.md) |
| Local development from source | [docs/local-development.md](docs/local-development.md) |
| Project architecture | [docs/architecture.md](docs/architecture.md) |
| Dashboard development | [docs/dashboard.md](docs/dashboard.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |

## Roadmap

- [x] Multi-store support (Epic + Steam)
- [x] PostgreSQL storage with Alembic migrations
- [x] REST API and web dashboard
- [x] Region-aware localization (one variable, derived defaults)
- [x] Review scores in notifications and dashboard
- [x] DLC differentiation
- [x] Pre-built Docker image on GHCR
- [x] Structured JSON logging for Loki/Grafana
- [ ] Multiple notification channels (Slack, Telegram, etc.) — [#55](https://github.com/JulioMoralesB/free-games-notifier/issues/55)

## License

This project is licensed under the [MIT License](LICENSE).

## Support

- 🐛 [Report an issue](https://github.com/JulioMoralesB/free-games-notifier/issues)
- 📦 [Container packages](https://github.com/JulioMoralesB/free-games-notifier/pkgs/container/free-games-notifier)
