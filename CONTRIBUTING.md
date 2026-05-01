# Contributing to Free Games Notifier

Thanks for your interest in contributing! This guide covers everything you need to know to get a development environment up and submit a useful pull request.

If you only want to **use** the project, see the [Self-hosting Guide](docs/self-hosting.md) instead.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind, assume good intent, and report unacceptable behaviour to the maintainer at <juliomoralesbd@gmail.com>.

## Reporting bugs and requesting features

Use the issue templates that appear automatically when you click **New Issue**. They prompt for the information that makes triage fast (repro steps, environment, expected vs actual). For security vulnerabilities, follow [SECURITY.md](SECURITY.md) — do **not** open a public issue.

## Branch model

```
feature branch ──► QA ──► main ──► tag vX.Y.Z ──► GHCR image
```

- All PRs target the **`QA`** branch — never `main` directly. `QA` accumulates changes until they are ready for a release; `main` is the source of truth for release tags.
- A maintainer fast-forwards `main` from `QA` and tags `vX.Y.Z` to publish a release. Pushing the tag triggers `.github/workflows/release.yml`, which builds the multi-arch Docker image and publishes it to `ghcr.io/juliomoralesb/free-games-notifier`.
- For a hotfix on `main` (e.g. broken release workflow), branch from `main`, target `QA` in the PR, and the maintainer cherry-picks or merges through normally.

## Local development

See [docs/local-development.md](docs/local-development.md) for the full step-by-step. The short version:

```bash
git clone https://github.com/JulioMoralesB/free-games-notifier.git
cd free-games-notifier

# Python backend
python3 -m venv env && source env/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # set DISCORD_WEBHOOK_URL at minimum

# Dashboard (only if you touch dashboard/)
cd dashboard && npm install && cd ..
```

## Running tests

```bash
# Python — 345 tests across api, scrapers, storage, dedupe, etc.
pytest tests/ -v -m "not integration and not production"

# Dashboard — Vitest + React Testing Library
cd dashboard && npm test

# Linter — fails CI if it has anything to say
ruff check .
ruff check . --fix   # auto-fix safe issues
```

CI runs all three on every PR (see `.github/workflows/tests.yml`). Get them green locally before pushing.

## Commit message style

We loosely follow [Conventional Commits](https://www.conventionalcommits.org/). Browse `git log --no-merges` for recent examples; the prefixes in active use are:

| Prefix | Use for |
|---|---|
| `feat:` | New user-visible functionality |
| `fix:` | Bug fixes |
| `refactor:` | Internal restructuring with no behaviour change |
| `chore:` | Tooling, dependencies, repo hygiene |
| `docs:` | Documentation-only changes |
| `test:` | Adding or fixing tests |
| `ci:` | GitHub Actions / release pipeline changes |

Scopes (`feat(scrapers): …`) are optional but encouraged for non-trivial PRs.

The body of the commit is more important than the title — explain **why** the change exists, what alternatives you considered, and any caveats. The diff already shows what changed.

## Pull requests

The PR template (auto-filled when you open a PR) asks for a Summary and a Test plan. Keep both honest:

- **Summary** — bullet points of the user-facing change. If the PR is purely internal, say so explicitly.
- **Test plan** — what you actually ran, not what should theoretically pass. CI will tell us if the tests themselves work.

Always include `Closes #N` in the PR body if the PR resolves an open issue. The GitHub Action that syncs the project board relies on this.

If you opened the issue and started working on it, add the `in-progress` label to the issue when you push the branch (or ask a maintainer to). The label drives the project board column.

## Where things live

A short orientation map. For the full architecture overview, read [docs/architecture.md](docs/architecture.md).

| If you are touching… | Read first |
|---|---|
| A scraper (Epic, Steam, …) | `modules/scrapers/`, [docs/architecture.md](docs/architecture.md) |
| The Discord notification format | `modules/notifier.py`, the `_TRANSLATIONS` table for i18n |
| The REST API | `api/` package, [docs/api.md](docs/api.md) |
| The dashboard | `dashboard/src/`, [docs/dashboard.md](docs/dashboard.md) |
| Database schema | `modules/database.py`, `alembic/versions/`, [docs/database-migrations.md](docs/database-migrations.md) |
| Configuration / env vars | `config.py`, [docs/configuration.md](docs/configuration.md) |
| Logging | `modules/logging_config.py` (structured JSON for Loki/Grafana) |

## Logging conventions

- Use a module-level logger: `logger = logging.getLogger(__name__)` — never `logging.info(...)` directly.
- Use lazy formatting: `logger.info("Found %d games", len(games))` — not f-strings. The format call is skipped when the level is filtered out.
- Logs are emitted as JSON. Promtail/Loki extract `level`, `service`, and `logger` fields automatically.

## Adding a new scraper

1. Create `modules/scrapers/yourstore.py` with a class that subclasses `Scraper` (in `base.py`).
2. Implement `store_name` and `fetch_free_games() -> list[FreeGame]`.
3. Register it in `modules/scrapers/__init__.py` so `get_enabled_scrapers(["yourstore"])` returns it.
4. Update [docs/configuration.md](docs/configuration.md) and the README's roadmap.

## Adding a new dashboard language

See the [Dashboard Developer Guide](docs/dashboard.md#adding-a-new-language) — TypeScript will report missing translation keys at compile time, and the parity test (`translations.test.ts`) catches runtime drift.

## Releases

Releases are **maintainer-driven**. The flow:

1. PRs are merged into `QA` and accumulate.
2. Maintainer merges `QA → main` once a coherent set of changes is ready.
3. Maintainer creates an annotated tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. The release workflow builds and publishes the image. Self-hosters update via `docker compose pull && docker compose up -d`.

Pre-release tags (`vX.Y.Z-rc.1`) are supported and skip the `:latest` tag automatically — useful for testing the published image before the official release.

## Getting help

If you're stuck, open a draft PR or issue and tag it with `question`. Don't sit on a problem alone — the maintainer is friendly and the codebase isn't huge.
