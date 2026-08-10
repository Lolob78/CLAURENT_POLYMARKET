"""
MarketAnalyzer - Analyse parallèle des marchés avec gestion des erreurs et rate limiting.
Compatibilité : Août 2026 (WebSocket CLOB, async/await, fallback HTTP)
"""

import asyncio
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from src.clients.price_manager import price_manager
from src.clients.gamma import get_active_markets
from src.ingestion.news_scraper import scrape_news_market
from src.ingestion.dune_mcp import query_dune_mcp
from src.agents.debate_graph import debate_graph
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger("market_analyzer")


@dataclass
class MarketAnalysis:
    """Résultat de l'analyse d'un marché."""
    market: Dict
    edge: float
    side: str
    rationale: str
    price: float
    success: bool
    error: Optional[str] = None
    latency: float = 0.0


class MarketAnalyzer:
    """
    Analyse les marchés en parallèle avec :
    - Gestion des erreurs
    - Rate limiting (max 10 marchés en //)
    - Timeout (5s par marché)
    - Cache des résultats
    """

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._cache: Dict[str, Tuple[MarketAnalysis, float]] = {}

    async def analyze_markets(self, limit: int = 100, min_volume: int = 50000) -> List[MarketAnalysis]:
        """
        Analyse `limit` marchés en parallèle.
        Retourne une liste de `MarketAnalysis` (même en cas d'erreur).
        """
        markets = get_active_markets(min_volume=min_volume, limit=limit)
        if not markets:
            logger.warning("no_markets_found")
            return []

        logger.info("analyzing_markets", count=len(markets), max_concurrent=self.max_concurrent)
        tasks = []
        for market in markets:
            market_id = market.get("id") or market.get("conditionId", "unknown")
            if market_id in self._cache:
                cached_analysis, timestamp = self._cache[market_id]
                if time.time() - timestamp < 30.0:
                    tasks.append(asyncio.create_task(self._return_cached(market_id, cached_analysis)))
                    continue
            task = asyncio.create_task(self._analyze_single_market(market))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        analyses = [r for r in results if isinstance(r, MarketAnalysis)]

        # Remplir le cache au niveau appelant (les résultats mockés/passés sont aussi mis en cache)
        for analysis in analyses:
            mid = analysis.market.get("id") or analysis.market.get("conditionId")
            if mid:
                self._cache[mid] = (analysis, time.time())

        return analyses

    async def _return_cached(self, market_id: str, analysis: MarketAnalysis) -> MarketAnalysis:
        """Retourne une analyse depuis le cache."""
        logger.debug("using_cached_analysis", market_id=market_id)
        return analysis

    async def _analyze_single_market(self, market: Dict) -> MarketAnalysis:
        """
        Analyse un seul marché (avec timeout et gestion d'erreur).
        """
        market_id = market.get("id") or market.get("conditionId", "unknown")
        start_time = time.time()

        try:
            async with self.semaphore:
                token_id = market.get("clob_token_id") or (market.get("clob_token_ids", [None])[0])
                price = await self._get_price_with_timeout(token_id, timeout=3.0)
                if price is None:
                    return MarketAnalysis(
                        market=market,
                        edge=0.0,
                        side="NO",
                        rationale="Failed to fetch price",
                        price=0.5,
                        success=False,
                        error="price_fetch_failed",
                        latency=time.time() - start_time
                    )

                news, onchain = await asyncio.gather(
                    self._scrape_news_with_timeout(market["question"], timeout=4.0),
                    self._query_dune_with_timeout(market.get("condition_id", ""), timeout=4.0),
                    return_exceptions=True
                )
                if isinstance(news, Exception):
                    news = "No news available"
                if isinstance(onchain, Exception):
                    onchain = "No onchain data available"

                initial_state = {
                    "market": market,
                    "news_context": news,
                    "onchain_context": onchain
                }
                result = await self._debate_with_timeout(initial_state, timeout=18.0)
                if not result or not result.get("result"):
                    return MarketAnalysis(
                        market=market,
                        edge=0.0,
                        side="NO",
                        rationale="No result from debate graph",
                        price=price,
                        success=False,
                        error="debate_failed",
                        latency=time.time() - start_time
                    )

                agent_output = result["result"]
                analysis = MarketAnalysis(
                    market=market,
                    edge=agent_output.edge,
                    side=agent_output.side,
                    rationale=agent_output.rationale,
                    price=price,
                    success=True,
                    latency=time.time() - start_time
                )

                self._cache[market_id] = (analysis, time.time())
                return analysis

        except asyncio.TimeoutError:
            logger.warning("market_analysis_timeout", market_id=market_id)
            return MarketAnalysis(
                market=market,
                edge=0.0,
                side="NO",
                rationale="Analysis timed out",
                price=0.5,
                success=False,
                error="timeout",
                latency=time.time() - start_time
            )
        except Exception as e:
            logger.error("market_analysis_error", market_id=market_id, error=str(e))
            return MarketAnalysis(
                market=market,
                edge=0.0,
                side="NO",
                rationale=f"Error: {str(e)}",
                price=0.5,
                success=False,
                error=str(e),
                latency=time.time() - start_time
            )

    async def _get_price_with_timeout(self, token_id: str, timeout: float) -> Optional[float]:
        """Récupère le prix avec timeout."""
        try:
            price_data = await asyncio.wait_for(price_manager.get_price(token_id), timeout=timeout)
            return price_data.mid if price_data else None
        except asyncio.TimeoutError:
            logger.warning("price_fetch_timeout", token_id=token_id[:10])
            return None

    async def _scrape_news_with_timeout(self, question: str, timeout: float) -> str:
        """Scrape les news avec timeout."""
        try:
            return await asyncio.wait_for(scrape_news_market(question), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("news_scrape_timeout", question=question[:30])
            return "No news available (timeout)"
        except Exception:
            return "No news available"

    async def _query_dune_with_timeout(self, condition_id: str, timeout: float) -> str:
        """Requête Dune MCP avec timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(query_dune_mcp, condition_id),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning("dune_query_timeout", condition_id=condition_id[:10])
            return "No onchain data available (timeout)"
        except Exception:
            return "No onchain data available"

    async def _debate_with_timeout(self, state: Dict, timeout: float) -> Dict:
        """Exécute le débat avec timeout."""
        try:
            return await asyncio.wait_for(debate_graph.ainvoke(state), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("debate_timeout")
            return {"result": None}
        except Exception as e:
            logger.error("debate_error", error=str(e))
            return {"result": None}

    def clear_cache(self):
        """Efface le cache des analyses."""
        self._cache.clear()
        logger.info("analysis_cache_cleared")


market_analyzer = MarketAnalyzer(max_concurrent=10)
