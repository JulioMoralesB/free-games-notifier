"""Base scraper class defining the interface for game scrapers."""

from abc import ABC, abstractmethod

from modules.models import FreeGame


class BaseScraper(ABC):
    """Abstract base class for game store scrapers."""

    @property
    @abstractmethod
    def store_name(self) -> str:
        """Name of the game store (e.g., 'epic', 'steam')."""
        pass

    @abstractmethod
    def fetch_free_games(self) -> list[FreeGame]:
        """Fetch free games from the store.

        Returns
        -------
        list[FreeGame]
            List of free game promotions available from the store.
        """
        pass
