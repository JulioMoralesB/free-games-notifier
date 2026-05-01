"""Game deduplication logic for the scheduler.

Determines which scraped games are *new* compared to what was previously
seen, while guarding against three classes of false positives:

1. **Active duplicates** — a previously-seen URL whose promo is still running.
2. **Recently-expired URLs** — a URL whose promo just ended; the store may
   briefly return a wrong ``end_date`` (e.g. Steam off-by-one-year) and we
   suppress re-notifications for a grace window after expiry.
3. **Exact (URL, end_date) replays** — never re-notify a pair we have
   already persisted.

The functions here are pure: no I/O, no scheduling, no external dependencies
beyond ``datetime``.  They are easy to test in isolation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: Window after a promotion's expiry during which re-notification is suppressed,
#: even if the store returns a fresh-looking ``end_date``.  Tunable; 24 hours
#: matches the typical Epic / Steam free-promo cadence.
RECENTLY_EXPIRED_GRACE_PERIOD_HOURS = 24


def _normalize_end_date(end_date: str | None) -> str | None:
    """Normalize an end_date string to a canonical form for deduplication keys.

    Converts the ``Z`` UTC suffix to ``+00:00`` so that equivalent timestamps
    stored in different ISO 8601 forms are treated as the same key and don't
    trigger duplicate notifications.
    """
    if not end_date:
        return end_date
    normalized = end_date.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return normalized


def is_still_active(game) -> bool:
    """Return True if *game*'s promotion has not yet expired.

    Games with an empty or un-parseable ``end_date`` are treated as still-active
    to avoid false "new game" alerts caused by transient scraping failures.
    """
    end_date = game.end_date
    if not end_date:
        return True

    normalized = _normalize_end_date(end_date)

    try:
        ends_at = datetime.fromisoformat(normalized)
    except ValueError:
        # Keep legacy/malformed records from causing false "new" alerts.
        return True

    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)

    return ends_at >= datetime.now(timezone.utc)


def _recently_expired_urls(previous_games) -> set[str]:
    """Return URLs whose promo expired within the last grace period.

    Steam (and other stores) occasionally return a wrong ``end_date`` for a game
    whose promo just ended (e.g. off-by-one year).  Without this guard, a URL
    that expired minutes ago would pass both the ``previous_active_urls`` and
    ``previous_seen`` checks and trigger a duplicate notification.
    """
    now = datetime.now(timezone.utc)
    grace = timedelta(hours=RECENTLY_EXPIRED_GRACE_PERIOD_HOURS)
    urls: set[str] = set()
    for game in previous_games:
        if not game.url or not game.end_date:
            continue
        normalized = _normalize_end_date(game.end_date)
        try:
            ends_at = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        if ends_at < now <= ends_at + grace:
            urls.add(game.url)
    return urls


def find_new_games(current_games, previous_games):
    """Return games that are newly free compared to still-active previous promos.

    Three checks prevent duplicate notifications:

    1. ``previous_active_urls`` — URLs whose promos are still running.  A game
       whose URL is already active is suppressed regardless of its end_date.
    2. ``recently_expired_urls`` — URLs whose promo ended within the last
       :data:`RECENTLY_EXPIRED_GRACE_PERIOD_HOURS` hours.  This prevents a store
       returning a bad end_date (e.g. wrong year) right after expiry from
       triggering a re-notification for the same promotion.
    3. ``previous_seen`` — (url, end_date) pairs ever persisted.  Prevents
       re-notification for an expired promo even if the URL no longer appears
       in the active set.

    A game that passes *all* checks is genuinely new or has started a fresh
    promo with a different end_date after the grace period.

    Same-run deduplication: ``notified_urls`` tracks URLs already added to
    ``new_games`` in this loop so that a URL appearing twice in
    ``current_games`` (e.g. duplicate search-result rows) is only notified
    once.
    """
    # A (url, end_date) pair that already appeared in previous games should not
    # trigger a new notification, regardless of whether the promo is still active.
    # This prevents re-notifying for the same expired promo while still allowing
    # re-notification when the same game has a new promo (different end_date).
    previous_seen = {
        (game.url, _normalize_end_date(game.end_date))
        for game in previous_games
        if game.url
    }

    # Also track active URLs to suppress games seen before whose promos are still running.
    previous_active_urls = {
        game.url
        for game in previous_games
        if game.url and is_still_active(game)
    }

    # Suppress re-notification for URLs whose promo just expired — store data
    # errors (e.g. Steam returning a wrong year) would otherwise bypass both
    # previous_active_urls and previous_seen when the end_date differs.
    recently_expired = _recently_expired_urls(previous_games)

    new_games = []
    notified_urls: set[str] = set()
    for game in current_games:
        url = game.url
        if url:
            if (
                url not in previous_active_urls
                and url not in recently_expired
                and (url, _normalize_end_date(game.end_date)) not in previous_seen
                and url not in notified_urls
            ):
                new_games.append(game)
                notified_urls.add(url)
            continue

        # Fallback for malformed records that do not have a url.
        if game not in previous_games:
            new_games.append(game)

    return new_games
