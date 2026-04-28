"""Epic Games Store scraper implementation."""

import logging

import requests

from config import EPIC_GAMES_API_URL, EPIC_GAMES_REGION
from modules.models import FreeGame
from modules.retry import with_retry
from modules.scrapers.base import BaseScraper
from modules.scrapers.review_sources import fetch_metacritic_score

logger = logging.getLogger(__name__)

_RETRYABLE_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)


class EpicGamesScraper(BaseScraper):
    """Scraper for Epic Games Store free game promotions."""

    @property
    def store_name(self) -> str:
        """Store name identifier."""
        return "epic"

    def fetch_free_games(self) -> list[FreeGame]:
        """Fetch free games from Epic Games API.

        Returns
        -------
        list[FreeGame]
            List of free games currently available on Epic Games Store.
        """
        logger.info(f"Fetching free games from Epic Games API. URI: {EPIC_GAMES_API_URL}")
        try:
            response = with_retry(
                func=lambda: requests.get(EPIC_GAMES_API_URL, timeout=10),
                max_attempts=4,
                base_delay=1,
                retryable_exceptions=_RETRYABLE_ERRORS,
                description="Epic Games API fetch",
            )
        except _RETRYABLE_ERRORS as e:
            logger.error("Failed to fetch Epic Games API after retries: %s", e, exc_info=True)
            return []

        if response.status_code != 200:
            logger.error(f"Failed to fetch Epic Games API. Status Code: {response.status_code}")
            return []

        data = response.json()
        logger.info(f"Response obtained from Epic Games API. Response Keys: {list(data.keys())}")
        games = []

        for game in data["data"]["Catalog"]["searchStore"]["elements"]:
            price_info = game.get("price", {}).get("totalPrice", {})
            if price_info.get("discountPrice", 1) == 0:
                original_price_int = price_info.get("originalPrice", 0)
                if original_price_int > 0:
                    fmt = price_info.get("fmtPrice", {})
                    original_price = fmt.get("originalPrice") or None
                    if original_price == "0":
                        original_price = None
                else:
                    original_price = None
                ## Get the game title
                title = game["title"]
                logger.info(f"Found free game!: {title}")

                ## Get the game link
                game_id = ""
                ## If the game is a mystery game, skip it
                if "Mystery Game" in title:
                    logger.info("Mystery Game found, skipping.")
                    continue

                ## Try to get the offer page slug
                try:
                    offer_page_slug = game["offerMappings"][0]["pageSlug"]
                    if offer_page_slug:
                        logger.info(f"Found Offer Page Slug: {offer_page_slug}")
                        game_id = offer_page_slug

                except IndexError:
                    logger.info("No Offer Page Slug found.")
                ## If it fails, try to get the catalogNs page slug
                if not game_id:
                    try:
                        page_slug = game["catalogNs"]["mappings"][0]["pageSlug"]
                        if page_slug:
                            logger.info(f"Found CatalogNs Page Slug: {page_slug}")
                            game_id = page_slug
                    except IndexError:
                        logger.info("No CatalogNs Page Slug found.")
                ## If it fails, try to get the product slug
                if not game_id:
                    try:
                        product_slug = game["productSlug"]
                        if product_slug:
                            logger.info(f"Found Product Slug: {product_slug}")
                            game_id = product_slug
                    except KeyError:
                        logger.info("No Product Slug found.")

                ## If game_id is found, use it to create the link
                if game_id:
                    logger.info(f"Using game_id: {game_id}")
                    link = f"https://store.epicgames.com/{EPIC_GAMES_REGION}/p/{game_id}"
                ## If not, use the default link
                else:
                    logger.info("No game url found, using default link.")
                    link = f"https://store.epicgames.com/{EPIC_GAMES_REGION}/free-games"

                end_date = ""
                promotions = game.get("promotions")
                logger.debug(f"Promotions payload: {promotions}")
                logger.info(f"Promotions present: {bool(promotions)}")
                #If there are no promotional offers, skip the game
                if not promotions or not promotions.get("promotionalOffers"):
                    logger.info("No promotional offers found, skipping.")
                    continue
                for offer in promotions["promotionalOffers"][0]["promotionalOffers"]:
                    if offer["discountSetting"]["discountPercentage"] == 0:
                        end_date = offer["endDate"]
                        break
                logger.info(f"Computed end_date: {end_date}")

                description = game["description"]
                logger.info(f"Description: {description}")
                logger.info("Trying to find thumbnail.")
                thumbnail = ""
                for image in game["keyImages"]:
                    if image["type"] == "Thumbnail":
                        thumbnail = image["url"]
                        logger.info(f"Found Thumbnail: {thumbnail}")
                        break
                if not thumbnail:
                    logger.info("No Thumbnail found, trying a different image.")
                    thumbnail = game["keyImages"][0]["url"]
                if not thumbnail:
                    logger.info("No image found, using default.")
                    thumbnail = "https://static-assets-prod.epicgames.com/epic-store/static/webpack/25c285e020572b4f76b770d6cca272ec.png"
                logger.info(f"Thumbnail to be used: {thumbnail}")

                # Collect review scores from all available sources.
                review_scores = []
                mc = fetch_metacritic_score(title)
                if mc:
                    review_scores.append(mc)
                logger.info("Review scores for %r: %s", title, review_scores)

                games.append(
                    FreeGame(
                        title=title,
                        store=self.store_name,
                        url=link,
                        image_url=thumbnail,
                        original_price=original_price,
                        end_date=end_date,
                        is_permanent=False,
                        description=description,
                        game_type="game",
                        review_scores=review_scores,
                    )
                )
        logger.info(f"Returning {len(games)} games")
        logger.debug(f"Returning game titles: {[game.title for game in games]}")
        return games
