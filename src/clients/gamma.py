"""Client Gamma API pour récupérer les marchés Polymarket."""
import requests
from src.config import settings


def get_active_markets(min_volume: int = 50000, limit: int = 100):
    """Gamma API - marchés liquides (public, pas d'auth)"""
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "active": "true",
        "closed": "false",
        "order": "volume24hrClob",
        "ascending": "false",
        "limit": limit
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        markets = resp.json()
        
        # Filtrage liquidité - convertir en int pour éviter les erreurs de type
        filtered = []
        for m in markets:
            try:
                volume = float(m.get("volume24hrClob", 0))
                liquidity = float(m.get("liquidity", 0))
                if volume >= min_volume and liquidity > 20000:
                    filtered.append(m)
            except (ValueError, TypeError):
                continue  # Ignorer les marchés avec données invalides
        
        print(f"✅ {len(filtered)} marchés liquides trouvés")
        return filtered
    except Exception as e:
        print(f"Erreur Gamma API: {e}")
        return []