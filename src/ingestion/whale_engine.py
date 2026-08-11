"""Moteur de contexte whale/smart-money pour l'analyse des marchés.

Principe : le prix de marché ne montre pas QUI accumule. En suivant les
positions des top traders rentables (leaderboard officiel Polymarket), on
donne au judge un signal informationnel que le prix n'intègre pas encore.

Sources (gratuites, sans clé) :
- GET /v1/leaderboard            → top traders par PnL réel
- GET /positions?user=<wallet>   → positions ouvertes d'un trader

Optimisation latence : on précharge le leaderboard + les positions de tous
les top traders en parallèle (~1-2s), on indexe par condition_id, puis
chaque analyse fait un lookup O(1) — compatible avec le cycle 24/7.
"""
import asyncio
from typing import Dict, List, Optional

import aiohttp

from src.utils.logger import get_logger

logger = get_logger("whale_engine")

DATA = "https://data-api.polymarket.com"
HEADERS = {"User-Agent": "CLAURENT-Polymarket-Bot/1.0"}
LEADERBOARD_LIMIT = 25          # nb de top traders suivis
MIN_PNL = 20000                 # seuil de PnL pour être considéré "smart money"
_LEADERBOARD_TTL = 600          # recharger le leaderboard toutes les 10 min


class WhaleEngine:
    def __init__(self):
        self._top_traders: List[Dict] = []
        self._positions_index: Dict[str, List[Dict]] = {}  # condition_id -> positions
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _fetch_json(self, session, url: str, params: dict) -> Optional[dict]:
        try:
            async with session.get(url, params=params, headers=HEADERS,
                                    timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.warning("whale_fetch_error", url=url[:40], error=str(e))
        return None

    async def _load_leaderboard(self, session) -> None:
        """Charge le top traders + leurs positions en parallèle, indexe par marché."""
        data = await self._fetch_json(session, f"{DATA}/v1/leaderboard", {})
        if not isinstance(data, list) or not data:
            logger.warning("whale_leaderboard_empty")
            return
        # Garder les traders rentables
        self._top_traders = [
            t for t in data
            if float(t.get("pnl", 0) or 0) >= MIN_PNL
        ][:LEADERBOARD_LIMIT]

        # Récupérer les positions de chaque top trader en parallèle
        wallets = [t["proxyWallet"] for t in self._top_traders]
        positions = await asyncio.gather(*[
            self._fetch_json(session, f"{DATA}/positions", {"user": w, "limit": 50})
            for w in wallets
        ])

        # Indexer par condition_id, en annotant le pnl du trader
        index: Dict[str, List[Dict]] = {}
        for trader, pos_list in zip(self._top_traders, positions):
            if not isinstance(pos_list, list):
                continue
            pnl = float(trader.get("pnl", 0) or 0)
            for p in pos_list:
                cond = p.get("conditionId")
                if not cond:
                    continue
                size_usd = float(p.get("size", 0) or 0) * float(p.get("curPrice") or p.get("avgPrice") or 0)
                # Convention : outcomeIndex 0 = YES, 1 = NO
                side = "YES" if int(p.get("outcomeIndex", 0)) == 0 else "NO"
                if (p.get("curPrice") or 0) <= 0:
                    continue  # position résolue, on ne la compte pas
                entry = {
                    "user": trader.get("userName") or trader["proxyWallet"][:10],
                    "pnl": pnl,
                    "side": side,
                    "size": float(p.get("size", 0) or 0),
                    "size_usd": size_usd,
                    "avg": float(p.get("avgPrice", 0) or 0),
                }
                index.setdefault(cond, []).append(entry)
        self._positions_index = index
        self._loaded_at = asyncio.get_event_loop().time()
        logger.info("whale_loaded", traders=len(self._top_traders),
                    markets=len(index))

    async def ensure_loaded(self) -> None:
        """Recharge si le cache est périmé."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            if not self._top_traders or (now - self._loaded_at) > _LEADERBOARD_TTL:
                async with aiohttp.ClientSession() as session:
                    await self._load_leaderboard(session)

    async def get_context(self, condition_id: str) -> str:
        """Contexte whale pour un marché (lookup indexé, O(1))."""
        await self.ensure_loaded()
        pos = self._positions_index.get(condition_id, [])
        if not pos:
            return "No smart-money position on this market."
        # Trier par taille USD décroissante
        pos.sort(key=lambda x: -x["size_usd"])
        lines = []
        for p in pos[:4]:
            lines.append(
                f"- {p['user']} (PnL ${p['pnl']:,.0f}): {p['side']} "
                f"${p['size_usd']:,.0f} @ {p['avg']:.3f}"
            )
        logger.info("whale_signal", market=condition_id[:12], positions=len(pos))
        return "\n".join(lines)


whale_engine = WhaleEngine()
