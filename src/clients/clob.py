import aiohttp

CLOB_HOST = "https://clob.polymarket.com"


async def get_live_price(token_id: str) -> float:
    """Prix live depuis le CLOB Polymarket (Level 0, pas d'auth).
    Fallback à 0.5 si le token_id est absent ou l'API indisponible.
    """
    if not token_id:
        return 0.5
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CLOB_HOST}/midpoint",
                params={"token_id": token_id},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("mid", 0.5))
    except Exception:
        pass
    return 0.5
