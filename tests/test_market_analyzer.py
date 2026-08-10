"""Tests unitaires pour MarketAnalyzer."""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.analyzers.market_analyzer import MarketAnalyzer, MarketAnalysis


@pytest.mark.asyncio
async def test_market_analyzer_not_singleton():
    """Test que MarketAnalyzer n'est PAS un singleton (contrairement à PriceManager)."""
    ma1 = MarketAnalyzer()
    ma2 = MarketAnalyzer()
    assert ma1 is not ma2


@pytest.mark.asyncio
async def test_analyze_single_market_timeout():
    """Test le timeout dans l'analyse d'un marché."""
    ma = MarketAnalyzer(max_concurrent=1)
    with patch.object(ma, '_get_price_with_timeout', new_callable=AsyncMock) as mock_price, \
         patch.object(ma, '_scrape_news_with_timeout', new_callable=AsyncMock) as mock_news, \
         patch.object(ma, '_query_dune_with_timeout', new_callable=AsyncMock) as mock_dune, \
         patch.object(ma, '_debate_with_timeout', new_callable=AsyncMock) as mock_debate:

        # Simuler un timeout sur le prix
        mock_price.return_value = None
        mock_news.return_value = "News"
        mock_dune.return_value = "Onchain"
        mock_debate.return_value = {"result": None}

        market = {"id": "123", "question": "Test", "clob_token_id": "0x123"}
        result = await ma._analyze_single_market(market)

        assert result.success is False
        assert result.error == "price_fetch_failed"


@pytest.mark.asyncio
async def test_analyze_markets_parallel():
    """Test l'analyse parallèle de plusieurs marchés."""
    ma = MarketAnalyzer(max_concurrent=2)
    with patch.object(ma, '_analyze_single_market', new_callable=AsyncMock) as mock_analyze:
        mock_analyze.side_effect = [
            MarketAnalysis(market={"id": "1"}, edge=0.15, side="YES", rationale="Test", price=0.6, success=True, latency=1.0),
            MarketAnalysis(market={"id": "2"}, edge=0.05, side="NO", rationale="Test", price=0.5, success=True, latency=1.0),
        ]

        results = await ma.analyze_markets(limit=2)
        assert len(results) == 2
        assert results[0].edge == 0.15
        assert results[1].edge == 0.05


@pytest.mark.asyncio
async def test_cache_works():
    """Test que le cache fonctionne."""
    ma = MarketAnalyzer(max_concurrent=1)
    # Marché stable simulé (id cohérent entre get_active_markets et le résultat)
    fake_market = {"id": "123", "question": "Test market", "clob_token_id": "0x123"}
    with patch("src.analyzers.market_analyzer.get_active_markets", return_value=[fake_market]), \
         patch.object(ma, '_analyze_single_market', new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = MarketAnalysis(
            market=fake_market, edge=0.2, side="YES", rationale="Test", price=0.7, success=True, latency=0.5
        )

        # Première analyse (pas en cache)
        results1 = await ma.analyze_markets(limit=1)
        assert len(results1) == 1
        assert mock_analyze.call_count == 1

        # Deuxième analyse (en cache)
        results2 = await ma.analyze_markets(limit=1)
        assert len(results2) == 1
        assert mock_analyze.call_count == 1  # Toujours 1 (cache utilisé)


@pytest.mark.asyncio
async def test_max_concurrent_limit():
    """Test que le nombre de tâches concurrentes est limité."""
    ma = MarketAnalyzer(max_concurrent=2)
    with patch.object(ma, '_analyze_single_market', new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = MarketAnalysis(
            market={"id": "1"}, edge=0.1, side="YES", rationale="Test", price=0.6, success=True, latency=0.1
        )

        # Lancer 5 analyses avec max_concurrent=2
        results = await ma.analyze_markets(limit=5)
        assert len(results) == 5
        # Le semaphore limite à 2 tâches en parallèle
        assert ma.semaphore._value == 2
