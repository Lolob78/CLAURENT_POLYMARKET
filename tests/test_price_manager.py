"""Tests unitaires pour PriceManager."""
import pytest
import asyncio
from src.clients.price_manager import PriceManager, PriceData


@pytest.mark.asyncio
async def test_price_manager_singleton():
    """Test que PriceManager est un singleton."""
    pm1 = PriceManager()
    pm2 = PriceManager()
    assert pm1 is pm2


@pytest.mark.asyncio
async def test_get_price_fallback():
    """Test le fallback HTTP si WebSocket n'est pas démarré."""
    pm = PriceManager()
    # Ne pas démarrer le WebSocket
    price_data = await pm.get_price("0x123", use_cache=False)
    # Doit retourner None (pas de fallback sans WebSocket)
    assert price_data is None


@pytest.mark.asyncio
async def test_price_data_structure():
    """Test la structure de PriceData."""
    pd = PriceData(mid=0.65, bid=0.64, ask=0.66, spread=0.02, timestamp=123.0, source="websocket")
    assert pd.mid == 0.65
    assert pd.spread == 0.02
    assert pd.source == "websocket"


@pytest.mark.asyncio
async def test_price_manager_start_stop():
    """Test le démarrage et l'arrêt du PriceManager."""
    pm = PriceManager()
    await pm.start()
    assert pm._running is True
    await pm.stop()
    assert pm._running is False
