from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FreeGame:
    """A free-game promotion from any supported store.

    Fields
    ------
    title           : Display name of the game.
    store           : Identifier of the store that is offering the game for free, e.g. "epic".
    url             : URL to the game's store page.
    image_url       : URL to an image representing the game, e.g. a thumbnail.
    original_price  : The original price of the game, as a string, or ``None`` if not available. (e.g. "$19.99")
    end_date        : ISO-8601 UTC string for when the promotion ends.
    is_permanent    : Whether the promotion is permanent, as a boolean.
    description     : A short description of the game.
    review_scores   : List of review score strings from any number of sources, e.g.
                      ``["Very Positive", "Metascore: 83", "OpenCritic: 78"]``.
                      Empty list when no scores are available.
    game_type       : Content type — ``"game"`` (default) or ``"dlc"``.
    """

    title: str
    store: str
    url: str
    image_url: str
    original_price: Optional[str]
    end_date: str
    is_permanent: bool
    description: str = ""
    review_scores: list[str] = field(default_factory=list)
    game_type: str = "game"

    def to_dict(self) -> dict:
        """Return a plain dict representation of this FreeGame."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FreeGame":
        """Create a FreeGame from a dict, accepting both current and legacy field names.

        Handles two legacy formats transparently:
        - Old ``review_score`` string field → wrapped in a single-item list.
        - New ``review_scores`` list field → used as-is.
        """
        # New format: list; old format: single string → wrap; absent → empty list.
        raw_scores = data.get("review_scores")
        if isinstance(raw_scores, list):
            review_scores = raw_scores
        elif data.get("review_score"):
            review_scores = [data["review_score"]]
        else:
            review_scores = []

        return cls(
            title=data.get("title", ""),
            store=data.get("store", "epic"),
            url=data.get("url") or data.get("link", ""),
            image_url=data.get("image_url") or data.get("thumbnail", ""),
            original_price=data.get("original_price"),
            end_date=data.get("end_date", ""),
            is_permanent=data.get("is_permanent", False),
            description=data.get("description", ""),
            review_scores=review_scores,
            game_type=data.get("game_type", "game"),
        )
