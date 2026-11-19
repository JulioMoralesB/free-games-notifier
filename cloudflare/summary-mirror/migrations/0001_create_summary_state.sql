-- Latest /api/summary snapshot pushed by the notifier, plus freshness-alert state.
-- Always exactly zero or one row (id = 1).
CREATE TABLE IF NOT EXISTS summary_state (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    active_promotions   TEXT NOT NULL,  -- JSON array of {title, link, store, end_date}
    last_check_at       TEXT,           -- ISO-8601 UTC, from the notifier
    received_at         TEXT NOT NULL,  -- ISO-8601 UTC, when the mirror stored it
    stale_alert_sent_at TEXT            -- set once a freshness alert fires; cleared by the next push
);
