# Troubleshooting

## Common Issues

### 1. `ValueError: Discord webhook URL not configured in environment variables`
- **Problem**: Notification sending fails and the error is raised/logged by the scheduler
- **Solution**: Verify `DISCORD_WEBHOOK_URL` is set in `.env` and the webhook is valid
- **Check**: `grep DISCORD_WEBHOOK_URL .env`

### 2. ValueError when `DISCORD_WEBHOOK_URL` is missing
- **Problem**: Logs show a `ValueError` and notifications do not start because the Discord webhook URL is not configured
- **Solution**: Ensure `DISCORD_WEBHOOK_URL` is defined at minimum
- **Check**: `printenv | grep DISCORD`

### 3. Database connection errors
- **Problem**: `psycopg2.OperationalError: could not connect to server`
- **Solution**: Verify PostgreSQL credentials in `.env` or leave `DB_HOST` unset to use file storage
- **Check**: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`

### 4. No logs appearing
- **Problem**: `data/logs/notifier.log` doesn't exist
- **Solution**: `mkdir -p data/logs && touch data/logs/notifier.log`
- **Docker**: Mount volume: `-v $(pwd)/data/logs/notifier.log:/mnt/logs/notifier.log`

### 5. Games not detected
- **Problem**: Service runs but no notifications are sent
- **Solution**:
  - Check if the Epic Games API is responding (may be rate limited)
  - Verify the Discord webhook is still valid (webhooks can expire)
  - Check logs: `grep ERROR /mnt/logs/notifier.log`

### 6. Health check monitor failing
- **Problem**: Your configured health monitor reports the service as unhealthy
- **Solution**:
  - Verify `HEALTHCHECK_URL` points to a health endpoint that returns JSON
  - Confirm the response includes an `ok` field (for example: `{"ok": true}`)
  - Confirm `ENABLE_HEALTHCHECK=true` is set
  - Ensure the container has internet access

## Docker

```bash
# View logs
docker logs free-games-notifier

# Restart service
docker restart free-games-notifier

# Stop and remove
docker compose down
```
