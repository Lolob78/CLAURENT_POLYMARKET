"""Client Gamma API pour récupérer les marchés Polymarket."""
import requests
from src.config import settings
from rich.console import Console

console = Console()


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
    try:
        resp = requests.get(url, params=params, timeout=15)
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
        
        console.log(f"[green]✅ {len(filtered)} marchés liquides trouvés[/green]")
        return filtered
    except Exception as e:
        console.log(f"[red]Erreur Gamma API: {e}[/red]")
        return []