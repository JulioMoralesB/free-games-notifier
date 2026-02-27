import requests
from config import EPIC_GAMES_API_URL

import logging
logger = logging.getLogger(__name__)

def fetch_free_games():
    """Fetch free games from Epic Games API."""
    logger.info(f"Fetching free games from Epic Games API. URI: {EPIC_GAMES_API_URL}")
    response = requests.get(EPIC_GAMES_API_URL)
    
    if response.status_code != 200:
        logger.error(f"Failed to fetch Epic Games API. Status Code: {response.status_code}")
        return []
    
    data = response.json()
    logger.info(f"Response obtained from Epic Games API. Response Keys: {list(data.keys())}" )
    games = []

    for game in data["data"]["Catalog"]["searchStore"]["elements"]:
        price_info = game.get("price", {}).get("totalPrice", {})
        if price_info.get("discountPrice", 1) == 0:
            ## Get the game title
            title = game["title"]
            logger.info(f"Found free game!: {title}")
            
            ## Get the game link
            gameId = ""
            ## If the game is a mystery game, skip it
            if "Mystery Game" in title:
                logger.info("Mystery Game found, skipping.")
                continue
            
            ## Try to get the offer page slug
            try:
                offerPageSlug = game["offerMappings"][0]["pageSlug"]
                if offerPageSlug:
                    logger.info(f"Found Offer Page Slug: {offerPageSlug}")
                    gameId = offerPageSlug
            
            except IndexError:
                logger.info("No Offer Page Slug found.")
            ## If it fails, try to get the catalogNs page slug
            if not gameId:
                try:
                    pageSlug = game["catalogNs"]["mappings"][0]["pageSlug"]
                    if pageSlug:
                        logger.info(f"Found CatalogNs Page Slug: {pageSlug}")
                        gameId = pageSlug
                except IndexError:
                    logger.info("No CatalogNs Page Slug found.")
            ## If it fails, try to get the product slug
            if not gameId:
                try:
                    productSlug = game["productSlug"]
                    if productSlug:
                        logger.info(f"Found Product Slug: {productSlug}")
                        gameId = productSlug
                except KeyError:
                    logger.info("No Product Slug found.")
            
            ## If gameId is found, use it to create the link
            if gameId:
                logger.info(f"Using gameId: {gameId}")
                link = f"https://store.epicgames.com/es-MX/p/{gameId}"
            ## If not, use the default link
            else:
                logger.info("No game url found, using default link.")
                link = "https://store.epicgames.com/es-MX/free-games"    
                
            end_date = ""
            logger.info(f"Promotions: {game['promotions']}")
            #If there are no promotional offers, skip the game
            if not game["promotions"] or not game["promotions"].get("promotionalOffers"):
                logger.info("No promotional offers found, skipping.")
                continue
            for offer in game["promotions"]["promotionalOffers"][0]["promotionalOffers"]:
                if offer["discountSetting"]["discountPercentage"] == 0:
                    end_date = offer["endDate"]
                    break
            logger.info(f"End Date: {end_date}")

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

            games.append({"title": title, "link": link, "endDate": end_date, "description": description, "thumbnail": thumbnail})
    logger.info(f"Returning games: {games}")
    return games