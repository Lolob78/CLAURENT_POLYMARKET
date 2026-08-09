"""
Client Gamma API pour Polymarket (Août 2026).
Gère la pagination (limit=100 + cursor) et les métadonnées des marchés.
"""

import requests
from typing import List, Dict, Optional
from src.utils.logger import get_logger

logger = get_logger("gamma_client")


def get_active_markets(min_volume: int = 50000, limit: int = 100) -> List[Dict]:
    """
    Récupère les marchés actifs depuis Gamma API.
    Utilise la pagination 2026 (limit=100 + after_cursor).
    """
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "active": "true",
        "closed": "false",
        "order": "volume24hrClob",
        "ascending": "false",
        "limit": min(limit, 100)  # Max 100 par requête
    }
    headers = {
        "User-Agent": "CLAURENT-Polymarket-Bot/1.0",
        "Accept": "application/json",
    }

    all_markets = []
    after_cursor = None

    try:
        while len(all_markets) < limit:
            if after_cursor:
                params["after_cursor"] = after_cursor

            resp = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

            markets = data.get("markets", [])
            if not markets:
                break

            # Filtrer les marchés liquides
            filtered = []
            for m in markets:
                try:
                    volume = float(m.get("volume24hrClob", 0))
                    liquidity = float(m.get("liquidity", 0))
                    if volume >= min_volume and liquidity > 20000:
                        # Extraire les token_ids pour CLOB
                        m["clob_token_ids"] = (
                            m.get("clobTokenIds") or
                            m.get("tokenIds") or
                            [m.get("conditionId")] or
                            []
                        )
                        # Prendre le premier token_id par défaut
                        m["clob_token_id"] = m["clob_token_ids"][0] if m["clob_token_ids"] else None
                        filtered.append(m)
                except (ValueError, TypeError):
                    continue

            all_markets.extend(filtered)
            after_cursor = data.get("next_cursor")

            if not after_cursor or len(all_markets) >= limit:
                break

        logger.info("gamma_markets_fetched", count=len(all_markets))
        return all_markets[:limit]

    except Exception as e:
        logger.error("gamma_fetch_error", error=str(e))
        return []
