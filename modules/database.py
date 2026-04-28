import json
import logging

import psycopg2

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from modules.models import FreeGame

logger = logging.getLogger(__name__)

class FreeGamesDatabase:
    def __init__(self):
        self.conn_params = {
            "host": DB_HOST,
            "port": DB_PORT,
            "dbname": DB_NAME,
            "user": DB_USER,
            "password": DB_PASSWORD
        }

    def init_db(self):
        """Initialize the database by creating the schema and tables.

        Schema migrations (column type changes, etc.) are managed by Alembic.
        In normal deployments, migrations are applied automatically on service
        startup (see main.py) when ``DB_HOST`` is configured. Run
        ``alembic upgrade head`` manually only if you manage migrations
        outside the service startup flow (e.g., CI/CD or local maintenance).
        """
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:

                    # Ensure the schema exists before setting it as search path
                    cursor.execute("CREATE SCHEMA IF NOT EXISTS free_games")

                    # Set schema for this connection
                    cursor.execute("SET search_path TO free_games")

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS games (
                            id SERIAL PRIMARY KEY,
                            game_id TEXT UNIQUE NOT NULL,
                            title TEXT NOT NULL,
                            link TEXT NOT NULL,
                            description TEXT,
                            thumbnail TEXT,
                            promotion_end_date TEXT
                        )
                    """)

                    conn.commit()
                    logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    @staticmethod
    def _make_game_id(store: str, url: str) -> str:
        """Return a store-prefixed game ID to guarantee uniqueness across stores.

        Format: ``<store>:<url>``, e.g. ``epic:https://...`` or ``steam:https://...``.
        Raises :class:`ValueError` if either argument is empty so callers get a
        loud failure instead of a non-unique or empty identifier.
        """
        if not store or not url:
            raise ValueError(
                f"game_id requires non-empty store and url (got store={store!r}, url={url!r})"
            )
        return f"{store}:{url}"

    def get_games(self):
        """Retrieve all stored games from the database as a list of FreeGame objects."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET search_path TO free_games")
                    cursor.execute(
                        "SELECT title, link, description, thumbnail, "
                        "promotion_end_date, review_scores, store, game_type FROM games"
                    )
                    rows = cursor.fetchall()
                    games = [
                        FreeGame(
                            title=title,
                            store=store or "epic",
                            url=link,
                            image_url=thumbnail or "",
                            original_price=None,
                            end_date=end_date or "",
                            is_permanent=False,
                            description=description or "",
                            review_scores=(
                                json.loads(review_scores)
                                if review_scores
                                else []
                            ),
                            game_type=game_type or "game",
                        )
                        for title, link, description, thumbnail, end_date, review_scores, store, game_type in rows
                    ]
                    logger.debug(f"Retrieved {len(games)} games from database.")
                    return games
        except Exception as e:
            logger.error(f"Failed to retrieve games from database: {e}")
            raise

    def save_games(self, games):
        """Save games to the database, upserting records on conflict by game_id.

        ``game_id`` uses the ``<store>:<url>`` prefixed format so that records
        from different stores never collide even if they share similar URLs.
        """
        if not games:
            logger.warning("Attempted to save empty games list to database")
            return
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET search_path TO free_games")
                    for game in games:
                        if not game.url:
                            logger.warning(
                                f"Skipping game with missing url: {game.title}"
                            )
                            continue
                        game_id = self._make_game_id(game.store, game.url)
                        cursor.execute(
                            """
                            INSERT INTO games (game_id, title, link, description, thumbnail,
                                               promotion_end_date, review_scores, store, game_type)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (game_id) DO UPDATE SET
                                title = EXCLUDED.title,
                                link = EXCLUDED.link,
                                description = EXCLUDED.description,
                                thumbnail = EXCLUDED.thumbnail,
                                promotion_end_date = EXCLUDED.promotion_end_date,
                                review_scores = EXCLUDED.review_scores,
                                store = EXCLUDED.store,
                                game_type = EXCLUDED.game_type
                            """,
                            (
                                game_id,
                                game.title,
                                game.url,
                                game.description,
                                game.image_url,
                                game.end_date or None,
                                json.dumps(game.review_scores),
                                game.store,
                                game.game_type,
                            ),
                        )
                    conn.commit()
                    logger.info(f"Saved {len(games)} games to database.")
        except Exception as e:
            logger.error(f"Failed to save games to database: {e}")
            raise

    def insert_game(self, game):
        """Insert a game record into the database.

        *game* may be a dict with legacy keys or a :class:`FreeGame` instance.
        The ``game_id`` is derived using the ``<store>:<url>`` prefix format so
        that records remain unique across stores.
        """
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:

                    # Set schema for this connection
                    cursor.execute("SET search_path to free_games")

                    # Accept both dict (legacy) and FreeGame object.
                    if isinstance(game, dict):
                        store = game.get("store", "epic")
                        url = game.get("link") or game.get("url") or ""
                        if not url:
                            logger.warning(
                                f"Skipping game with missing url: {game.get('title')}"
                            )
                            return
                        game_id = self._make_game_id(store, url)
                        cursor.execute("""
                            INSERT INTO games (game_id, title, link, description, thumbnail,
                                               promotion_end_date, store)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (game_id) DO NOTHING
                        """, (
                            game_id,
                            game.get("title"),
                            url,
                            game.get("description"),
                            game.get("thumbnail"),
                            game.get("end_date"),
                            store,
                        ))
                    else:
                        if not game.url:
                            logger.warning(
                                f"Skipping game with missing url: {game.title}"
                            )
                            return
                        game_id = self._make_game_id(game.store, game.url)
                        cursor.execute("""
                            INSERT INTO games (game_id, title, link, description, thumbnail,
                                               promotion_end_date, store)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (game_id) DO NOTHING
                        """, (
                            game_id,
                            game.title,
                            game.url,
                            game.description,
                            game.image_url,
                            game.end_date or None,
                            game.store,
                        ))
                    conn.commit()
                    title = game.get("title") if isinstance(game, dict) else game.title
                    logger.info(f"Game '{title}' inserted successfully.")
        except Exception as e:
            title = game.get("title") if isinstance(game, dict) else getattr(game, "title", repr(game))
            logger.error(f"Failed to insert game '{title}': {e}")

    def get_all_games(self):
        """Retrieve all game records from the database."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:

                    # Set schema for this connection
                    cursor.execute("SET search_path to free_games")

                    cursor.execute("SELECT * FROM games")
                    games = cursor.fetchall()
                    logger.info(f"Retrieved {len(games)} games from the database.")
                    return games
        except Exception as e:
            logger.error(f"Failed to retrieve games: {e}")
            return []

    def save_last_notification(self, games):
        """Persist the last-sent notification batch as a JSON blob (single-row upsert)."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET search_path TO free_games")
                    serializable = [g.to_dict() for g in games]
                    cursor.execute(
                        """
                        INSERT INTO last_notification (id, games)
                        VALUES (1, %s)
                        ON CONFLICT (id) DO UPDATE SET games = EXCLUDED.games
                        """,
                        (json.dumps(serializable),),
                    )
                    conn.commit()
                    logger.info(f"Saved {len(games)} games to last_notification table.")
        except Exception as e:
            logger.error(f"Failed to save last notification to database: {e}")
            raise

    def get_last_notification(self):
        """Return the games list from the most recent notification as FreeGame objects, or [] if none stored."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET search_path TO free_games")
                    cursor.execute("SELECT games FROM last_notification WHERE id = 1")
                    row = cursor.fetchone()
                    if row is None:
                        return []
                    data = json.loads(row[0])
                    if not isinstance(data, list):
                        logger.error(
                            "Unexpected structure in last_notification table: expected list, "
                            f"got {type(data).__name__}"
                        )
                        return []
                    if not all(isinstance(game, dict) for game in data):
                        logger.error(
                            "Unexpected item types in last_notification table: expected list of dicts"
                        )
                        return []
                    return [FreeGame.from_dict(game) for game in data]
        except Exception as e:
            logger.error(f"Failed to retrieve last notification from database: {e}")
            raise

    def game_exists(self, game_id: str, store: str = "") -> bool:
        """Check if a game with the given game_id already exists in the database.

        *game_id* may be a plain URL **or** an already-prefixed ID
        (``<store>:<url>``).  When *store* is provided and *game_id* does not
        already carry a prefix the lookup is performed against the prefixed form.
        """
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:

                    # Set schema for this connection
                    cursor.execute("SET search_path to free_games")

                    # Build the prefixed key when needed.  Check for the
                    # store prefix explicitly — plain URLs already contain ":"
                    # (https://...) so a bare colon test would always skip this.
                    lookup_id = (
                        self._make_game_id(store, game_id)
                        if store and not game_id.startswith(f"{store}:")
                        else game_id
                    )
                    cursor.execute("SELECT 1 FROM games WHERE game_id = %s", (lookup_id,))
                    exists = cursor.fetchone() is not None
                    logger.debug(f"Game with ID '{lookup_id}' exists: {exists}")
                    return exists
        except Exception as e:
            logger.error(f"Failed to check if game exists: {e}")
            return False
