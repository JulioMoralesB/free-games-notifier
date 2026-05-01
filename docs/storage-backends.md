# Storage Backends

The notifier automatically selects a storage backend based on the `DB_HOST` environment variable.

| `DB_HOST` set? | Backend | Data location |
|---|---|---|
| ✅ Yes | PostgreSQL (`free_games` schema) | Remote database |
| ❌ No (default) | JSON file | `/mnt/data/free_games.json` (inside the container) |

## Which one should I use?

**Use the JSON file backend** if:
- You're running a single instance on a single machine
- You don't already have a PostgreSQL server
- You want zero external dependencies

**Use PostgreSQL** if:
- You already run a PostgreSQL server for other home-server services
- You want to query the data directly (e.g. for custom dashboards)
- You expect the game history to grow large enough that JSON parsing becomes noticeable
- You're running multiple instances that need to share state

## How the backends differ

### JSON file backend (default)

- Single file: `/mnt/data/free_games.json` (bind-mounted via `DATA_PATH` in `compose.yaml`)
- Loaded fully into memory on every check; suitable for thousands of games
- The container creates the file on first run if it doesn't exist
- Backups: copy the file

### PostgreSQL backend

- Schema: `free_games`, table: `games`
- `game_id` is derived from the game's `link` and used as the conflict key for upserts (`ON CONFLICT (game_id) DO UPDATE`)
- Schema is created automatically on startup, and any pending Alembic migrations are applied — no manual setup needed
- A second table, `last_notification`, stores the most recent Discord batch for the resend endpoint
- For migration details, see [Database Migrations](database-migrations.md)

## Switching from JSON to PostgreSQL

1. Stand up a PostgreSQL instance (any 13+ should work)
2. Add `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` to your `.env`
3. Start the container once so it can create the `free_games` schema and apply any pending migrations, then stop it again
4. (Optional) If you want to preserve history, import records from `free_games.json` into PostgreSQL via SQL
5. Start the container again. Existing JSON data is **not** auto-imported; use step 4 if you need to preserve history

## Switching from PostgreSQL to JSON

1. Remove or comment out the `DB_*` variables in `.env`
2. Restart the container — the service falls back to JSON file storage
3. PostgreSQL data is left untouched in the database; you can re-enable it later
