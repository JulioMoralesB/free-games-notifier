# Local Development

This guide covers running the service from source for development. For self-hosting via Docker, see the [Self-hosting Guide](self-hosting.md).

## Prerequisites

- Python 3.9+
- pip and `venv`
- Node.js 20+ and npm (only required to build or hot-reload the dashboard)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/JulioMoralesB/free-games-notifier.git
cd free-games-notifier
```

### 2. Create a virtual environment

```bash
python3 -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # for tests + linter
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

At minimum, set `DISCORD_WEBHOOK_URL` in `.env`. See the [Configuration Reference](configuration.md) for all options.

### 5. Run the scheduler

```bash
python main.py
```

The scheduler logs to `/mnt/logs/notifier.log` by default. For local development, you can override the log path or simply tail stdout — both file and console handlers receive every entry.

## Running the dashboard with hot-reload

Open a second terminal:

```bash
cd dashboard
npm install
npm run dev     # http://localhost:5173/dashboard/
```

The Vite dev server proxies `/games` requests to `http://localhost:8000`, so the Python API only needs to be running.

For production builds and instructions on adding a new language, see the [Dashboard Developer Guide](dashboard.md).

## Running tests

```bash
pytest tests/ -v
```

Tests cover both file-backend and PostgreSQL-backend paths. File-backend tests explicitly set `DB_HOST=None` to remain hermetic.

To run just the unit tests (excluding integration and production smoke tests):

```bash
pytest tests/ -v -m "not integration and not production"
```

## Linting

```bash
ruff check .
ruff check . --fix    # auto-fix safe issues
```

## Branch workflow

- All PRs target the `QA` branch — never `main` directly
- `main` is the source of truth for releases; tags `v*.*.*` push images to GHCR
- See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full contribution guide (once published)
