-- Game history mirrored from the notifier, served to the dashboard via
-- GET /games/history. Columns other than `item` exist only to filter and sort
-- in SQL exactly like the Python endpoint; `item` is returned as-is.
-- No secondary indexes: the table holds hundreds of rows, and every index
-- would add a row write per upsert against the Free plan's daily budget.
CREATE TABLE IF NOT EXISTS games (
    id         TEXT PRIMARY KEY,  -- "<store>:<link>"
    store      TEXT NOT NULL,
    title_sort TEXT NOT NULL,     -- lower-cased title (Python str.lower() equivalent)
    end_date   TEXT NOT NULL,     -- raw ISO-8601 text; sorted as text, like the Python API
    ends_at_ms INTEGER,           -- parsed end_date in epoch ms; NULL if empty/unparseable (counts as expired)
    item       TEXT NOT NULL,     -- the GameItem JSON served to the dashboard
    sync_id    TEXT NOT NULL      -- last full sync that included this game
);
