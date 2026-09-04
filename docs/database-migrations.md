# Database Migrations

Schema changes are managed by [Alembic](https://alembic.sqlalchemy.org/). Migration scripts live in `alembic/versions/` and are applied **automatically on startup**.

## Current migrations

| Revision | Description |
|----------|-------------|
| `0001`   | Initial schema — creates the `free_games` schema and `games` table |
| `0002`   | Widens `games.game_id` from `VARCHAR(255)` to `TEXT` |
| `0003`   | Converts `games.promotion_end_date` from `TIMESTAMP` to `TEXT` (ISO-8601 UTC) |
| `0004`   | Adds `last_notification` table for Discord resend support |
| `0005`   | Adds `games.review_score` |
| `0006`   | Adds `games.store` and migrates `game_id` to the `<store>:<url>` prefixed format |
| `0007`   | Adds `games.game_type` to distinguish standalone games from DLC |
| `0008`   | Renames `review_score` to `review_scores` and migrates it to a JSON array (multiple review sources per game) |

## Running migrations manually

Ensure `DATABASE_URL` is set, then run:

```bash
# Apply all pending migrations
alembic upgrade head

# Show current revision
alembic current

# Show migration history
alembic history --verbose

# Verify a table exists
psql "$DATABASE_URL" -c "SELECT to_regclass('free_games.last_notification');"

# Roll back one revision
alembic downgrade -1
```

Inside a Docker container:

```bash
docker exec free-games-notifier alembic upgrade head
```

## Creating a new migration

```bash
alembic revision -m "describe your change here"
# Edit the generated file in alembic/versions/ to add upgrade()/downgrade() logic
```
