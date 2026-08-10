"""
PriceManager - Gestion centralisée des prix Polymarket (WebSocket + Fallbacks).
Compatibilité : Août 2026 (CLOB V2, WebSocket ws-subscriptions-clob.polymarket.com)
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
from src.utils.logger import get_logger

logger = get_logger("price_manager")


@dataclass
class PriceData:
    """Données de prix pour un token/marché."""
    mid: float  # Prix médian (0-1)
    bid: Optional[float] = None  # Meilleur prix d'achat
    ask: Optional[float] = None  # Meilleur prix de vente
    spread: Optional[float] = None  # Spread (ask - bid)
    timestamp: float = 0.0  # Timestamp de la dernière mise à jour
    source: str = "unknown"  # "websocket", "clob_http", "gamma_http"


class PriceManager:
    """
    Gère les prix en temps réel via WebSocket CLOB, avec fallbacks HTTP.
    Singleton : une seule instance pour toute l'application.
    """

    _instance: Optional['PriceManager'] = None
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._prices: Dict[str, PriceData] = {}  # {token_id: PriceData}
        self._subscriptions: Dict[str, set] = {}  # {token_id: set(callbacks)}
        self._ws: Optional[aiohttp.ClientSession] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._reconnect_delay = 1.0  # Délai de reconnexion (secondes)
        self._last_pong = time.time()  # Dernier pong envoyé
        self._running = False

    async def start(self):
        """Démarre la connexion WebSocket et le cache."""
        if self._running:
            return
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_loop())
        logger.info("price_manager_started", ws_url=self.WS_URL)

    async def stop(self):
        """Arrête la connexion WebSocket."""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        logger.info("price_manager_stopped")

    async def _ws_loop(self):
        """Boucle principale de gestion du WebSocket."""
        while self._running:
            try:
                await self._connect_ws()
            except Exception as e:
                logger.error("ws_connection_error", error=str(e))
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 30.0)  # Backoff exponentiel

    async def _connect_ws(self):
        """Établit une connexion WebSocket et écoute les messages."""
        self._reconnect_delay = 1.0  # Reset du délai après une reconnexion réussie
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    self.WS_URL,
                    heartbeat=5.0,  # Ping toutes les 5s
                    autoping=True,  # aiohttp gère les pings automatiquement
                headers={"User-Agent": "CLAURENT-Polymarket-Bot/1.0"}
                    timeout=aiohttp.ClientTimeout(total=30.0)
                ) as ws:
                    self._ws = ws
                    logger.info("ws_connected", url=self.WS_URL)
                    self._last_pong = time.time()

                    # S'abonner à tous les token_ids déjà suivis
                    for token_id in self._prices:
                        await self._subscribe(token_id)

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_ws_message(msg.data)
                        elif msg.type == aiohttp.WSMsgType.PONG:
                            self._last_pong = time.time()
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            logger.warning("ws_closed", code=msg.extra)
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error("ws_error", error=ws.exception())
                            break
        except Exception as e:
            logger.error("ws_loop_error", error=str(e))

    async def _handle_ws_message(self, data: str):
        """Traite un message WebSocket."""
        try:
            msg = json.loads(data)
            topic = msg.get("topic")
            payload = msg.get("payload", {})

            if topic == "market" and "type" in msg:
                msg_type = msg["type"]
                if msg_type == "price_change":
                    token_id = payload.get("token_id")
                    if token_id:
                        price_data = PriceData(
                            mid=float(payload.get("mid", 0.5)),
                            bid=float(payload.get("bid")) if payload.get("bid") else None,
                            ask=float(payload.get("ask")) if payload.get("ask") else None,
                            spread=float(payload.get("spread")) if payload.get("spread") else None,
                            timestamp=time.time(),
                            source="websocket"
                        )
                        self._update_price(token_id, price_data)
                elif msg_type == "orderbook_snapshot":
                    token_id = payload.get("token_id")
                    if token_id:
                        # Extraire le midpoint depuis l'orderbook
                        bids = payload.get("bids", [])
                        asks = payload.get("asks", [])
                        mid = 0.5
                        if bids and asks:
                            best_bid = bids[0][0]  # [price, quantity]
                            best_ask = asks[0][0]
                            mid = (best_bid + best_ask) / 2
                        price_data = PriceData(
                            mid=mid,
                            bid=best_bid if bids else None,
                            ask=best_ask if asks else None,
                            spread=(best_ask - best_bid) if (bids and asks) else None,
                            timestamp=time.time(),
                            source="websocket"
                        )
                        self._update_price(token_id, price_data)
        except json.JSONDecodeError as e:
            logger.error("ws_json_parse_error", error=str(e), data=data[:100])
        except Exception as e:
            logger.error("ws_message_error", error=str(e))

    def _update_price(self, token_id: str, price_data: PriceData):
        """Met à jour le prix et notifie les callbacks."""
        old_price = self._prices.get(token_id)
        self._prices[token_id] = price_data

        # Notifier les callbacks
        if token_id in self._subscriptions:
            for callback in self._subscriptions[token_id]:
                try:
                    callback(token_id, price_data)
                except Exception as e:
                    logger.error("callback_error", token_id=token_id, error=str(e))

        # Log si le prix a changé significativement
        if old_price and abs(price_data.mid - old_price.mid) > 0.01:
            logger.info(
                "price_updated",
                token_id=token_id[:10] + "...",
                old_price=old_price.mid,
                new_price=price_data.mid,
                source=price_data.source
            )

    async def _subscribe(self, token_id: str):
        """S'abonne à un token_id via WebSocket."""
        if not self._ws or self._ws.closed:
            return
        try:
            # Polymarket WebSocket utilise un système de subscription implicite
            # (pas besoin de message explicite, les données arrivent automatiquement)
            # Mais on peut forcer un snapshot initial
            subscribe_msg = {
                "topic": "market",
                "type": "subscribe",
                "payload": {"token_ids": [token_id]}
            }
            await self._ws.send_json(subscribe_msg)
            logger.debug("ws_subscribed", token_id=token_id[:10])
        except Exception as e:
            logger.error("ws_subscribe_error", token_id=token_id, error=str(e))

    async def get_price(self, token_id: str, use_cache: bool = True) -> Optional[PriceData]:
        """
        Récupère le prix d'un token_id.
        1. D'abord le cache (WebSocket)
        2. Sinon, fallback CLOB HTTP
        3. Sinon, fallback Gamma HTTP
        """
        # 1. Vérifier le cache (WebSocket)
        if use_cache and token_id in self._prices:
            cached = self._prices[token_id]
            if time.time() - cached.timestamp < 5.0:  # Cache valide 5s
                return cached

        # 2. Fallback CLOB HTTP
        try:
            price = await self._fetch_clob_price(token_id)
            if price is not None:
                price_data = PriceData(
                    mid=price,
                    timestamp=time.time(),
                    source="clob_http"
                )
                self._prices[token_id] = price_data
                return price_data
        except Exception as e:
            logger.warning("clob_fallback_error", token_id=token_id, error=str(e))

        # 3. Fallback Gamma HTTP
        try:
            price = await self._fetch_gamma_price(token_id)
            if price is not None:
                price_data = PriceData(
                    mid=price,
                    timestamp=time.time(),
                    source="gamma_http"
                )
                self._prices[token_id] = price_data
                return price_data
        except Exception as e:
            logger.warning("gamma_fallback_error", token_id=token_id, error=str(e))

        return None

    async def _fetch_clob_price(self, token_id: str) -> Optional[float]:
        """Récupère le prix depuis CLOB HTTP."""
        url = f"{self.CLOB_API}/midprice/{token_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get("mid", 0.5))
        except Exception as e:
            logger.error("clob_fetch_error", token_id=token_id, error=str(e))
        return None

    async def _fetch_gamma_price(self, token_id: str) -> Optional[float]:
        """Récupère le prix depuis Gamma HTTP."""
        url = f"{self.GAMMA_API}/ticker"
        params = {"tokenId": token_id}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get("lastPrice", 0.5))
        except Exception as e:
            logger.error("gamma_fetch_error", token_id=token_id, error=str(e))
        return None

    def subscribe(self, token_id: str, callback: Callable[[str, PriceData], None]):
        """S'abonne aux mises à jour de prix pour un token_id."""
        if token_id not in self._subscriptions:
            self._subscriptions[token_id] = set()
        self._subscriptions[token_id].add(callback)
        # Si on a déjà le prix en cache, l'envoyer immédiatement
        if token_id in self._prices:
            callback(token_id, self._prices[token_id])

    def unsubscribe(self, token_id: str, callback: Callable[[str, PriceData], None]):
        """Se désabonne des mises à jour de prix."""
        if token_id in self._subscriptions:
            self._subscriptions[token_id].discard(callback)
            if not self._subscriptions[token_id]:
                del self._subscriptions[token_id]

    def get_all_prices(self) -> Dict[str, PriceData]:
        """Retourne tous les prix en cache."""
        return self._prices.copy()


# Instance globale
price_manager = PriceManager()
