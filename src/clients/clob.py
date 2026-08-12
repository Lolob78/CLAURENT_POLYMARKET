"""
Client CLOB pour Polymarket (V2 - Août 2026).
Utilise le PriceManager pour les prix temps réel.
"""

import aiohttp
from src.clients.price_manager import price_manager
from src.utils.logger import get_logger

logger = get_logger("clob_client")


async def get_live_price(token_id: str) -> float | None:
    """
    Récupère le prix live d'un token_id.
    Utilise le PriceManager (WebSocket + fallbacks).
    Retourne None si le prix réel n'est pas trouvé — JAMAIS de prix fictif.
    """
    if not token_id:
        logger.warning("clob_no_token_id")
        return None
    price_data = await price_manager.get_price(token_id)
    if price_data:
        return price_data.mid
    # Pas de prix réel disponible → None (le trade sera rejeté)
    logger.warning("clob_no_live_price", token_id=token_id)
    return None


async def get_orderbook(token_id: str) -> dict:
    """
    Récupère l'orderbook complet depuis CLOB HTTP.
    (Utilisé pour estimer le slippage)
    """
    if not token_id:
        return {"bids": [], "asks": []}

    url = f"https://clob.polymarket.com/orderbook/{token_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.error("orderbook_fetch_error", token_id=token_id, error=str(e))
    return {"bids": [], "asks": []}
