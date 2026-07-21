"""
Binance WebSocket client for real-time price tracking.
Manages WebSocket connections to Binance stream API.
"""

import asyncio
import json
import logging
import websockets
from typing import Callable, Dict, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ANSI colors so Binance WS activity is visually distinct in the console.
_COLOR_INFO = "\033[36m"    # cyan - connections/subscriptions
_COLOR_WARN = "\033[33m"    # yellow
_COLOR_ERROR = "\033[31m"   # red
_COLOR_DEBUG = "\033[90m"   # grey
_COLOR_RESET = "\033[0m"


def _c(color: str, text: str) -> str:
    return f"{color}{text}{_COLOR_RESET}"


@dataclass
class PriceUpdate:
    """Price update data from Binance trade stream"""
    symbol: str
    price: float
    event_time: int
    quantity: float = 0.0
    trade_id: int = 0
    trade_time: int = 0
    is_buyer_maker: bool = False


class BinanceWebSocketClient:
    """
    WebSocket client for Binance real-time price streaming.
    Manages multiple symbol subscriptions efficiently.
    """

    # Binance blocks or silently drops WebSocket handshakes from some cloud
    # regions/IPs (HTTP 451, or a handshake that just times out) on the
    # primary host. Mirror the REST fallback pattern in
    # challenge_monitor_service.py's _get_current_price/_get_price_at_time by
    # rotating through alternate hosts instead of retrying the same blocked
    # one forever. data-stream.binance.vision is Binance's public
    # "market data only" WS mirror — no auth needed, matches
    # data-api.binance.vision used for REST.
    BINANCE_WS_HOSTS = (
        "wss://stream.binance.com:9443/ws",
        "wss://stream.binance.com:443/ws",
        "wss://data-stream.binance.vision/ws",
    )

    def __init__(self):
        self._websocket = None
        self._running = False
        self._subscribed_symbols: Set[str] = set()
        self._callbacks: Dict[str, Callable[[PriceUpdate], None]] = {}
        self._lock = asyncio.Lock()
        self._reconnect_delay = 5  # seconds
        self._max_reconnect_delay = 60  # seconds
        self._message_id = 0
        self._host_index = 0

    async def start(self):
        """Start the WebSocket client with automatic reconnection"""
        self._running = True
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                logger.error(_c(_COLOR_ERROR, f"WebSocket error: {e}"))
                # Rotate to the next mirror host — a rejected (451) or timed-out
                # handshake on this host is likely to keep failing the same way.
                self._host_index += 1
                await asyncio.sleep(self._reconnect_delay)
                # Exponential backoff
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay
                )

    async def _connect(self):
        """Establish WebSocket connection and handle messages"""
        url = self.BINANCE_WS_HOSTS[self._host_index % len(self.BINANCE_WS_HOSTS)]
        logger.info(_c(_COLOR_INFO, f"Connecting to Binance WebSocket ({url})"))

        try:
            async with websockets.connect(url, open_timeout=15) as websocket:
                self._websocket = websocket
                self._reconnect_delay = 5  # Reset on successful connection

                # Subscribe to any existing symbols after reconnection
                async with self._lock:
                    if self._subscribed_symbols:
                        await self._send_subscribe(list(self._subscribed_symbols))

                async for message in websocket:
                    if not self._running:
                        break
                    await self._handle_message(message)

        except websockets.exceptions.ConnectionClosed:
            logger.warning(_c(_COLOR_WARN, "WebSocket connection closed"))
            raise
        except Exception as e:
            logger.error(_c(_COLOR_ERROR, f"WebSocket error connecting to {url}: {e}"))
            raise

    async def _send_subscribe(self, symbols: list[str]):
        """Send SUBSCRIBE message to add streams"""
        if not self._websocket or not symbols:
            return

        self._message_id += 1
        params = [f"{symbol.lower()}@trade" for symbol in symbols]
        message = {
            "method": "SUBSCRIBE",
            "params": params,
            "id": self._message_id
        }

        try:
            await self._websocket.send(json.dumps(message))
            logger.info(_c(_COLOR_INFO, f"Subscribed to streams: {params}"))
        except Exception as e:
            logger.error(_c(_COLOR_ERROR, f"Failed to send subscribe message: {e}"))
            raise

    async def _send_unsubscribe(self, symbols: list[str]):
        """Send UNSUBSCRIBE message to remove streams"""
        if not self._websocket or not symbols:
            return

        self._message_id += 1
        params = [f"{symbol.lower()}@trade" for symbol in symbols]
        message = {
            "method": "UNSUBSCRIBE",
            "params": params,
            "id": self._message_id
        }

        try:
            await self._websocket.send(json.dumps(message))
            logger.info(_c(_COLOR_INFO, f"Unsubscribed from streams: {params}"))
        except Exception as e:
            logger.error(_c(_COLOR_ERROR, f"Failed to send unsubscribe message: {e}"))
            raise

    async def _handle_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            
            # Handle single stream trade data
            # e = event type, E = event time, s = symbol, t = trade ID
            # p = price, q = quantity, T = trade time, m = is buyer maker
            if "e" in data and data["e"] == "trade":
                symbol = data["s"]
                price = float(data["p"])
                quantity = float(data["q"])
                event_time = data.get("E", 0)
                trade_id = data.get("t", 0)
                trade_time = data.get("T", 0)
                is_buyer_maker = data.get("m", False)

                price_update = PriceUpdate(
                    symbol=symbol,
                    price=price,
                    event_time=event_time,
                    quantity=quantity,
                    trade_id=trade_id,
                    trade_time=trade_time,
                    is_buyer_maker=is_buyer_maker
                )

                # Notify callback if registered
                callback = self._callbacks.get(symbol.upper())
                if callback:
                    try:
                        result = callback(price_update)
                        # Support both async and sync callbacks
                        if asyncio.iscoroutine(result):
                            asyncio.create_task(result)
                    except Exception as e:
                        logger.error(_c(_COLOR_ERROR, f"Error in price callback for {symbol}: {e}"))

            # Handle combined stream wrapper
            elif "data" in data:
                inner_data = data["data"]
                if inner_data.get("e") == "trade":
                    symbol = inner_data["s"]
                    price = float(inner_data["p"])
                    quantity = float(inner_data["q"])
                    event_time = inner_data.get("E", 0)
                    trade_id = inner_data.get("t", 0)
                    trade_time = inner_data.get("T", 0)
                    is_buyer_maker = inner_data.get("m", False)

                    price_update = PriceUpdate(
                        symbol=symbol,
                        price=price,
                        event_time=event_time,
                        quantity=quantity,
                        trade_id=trade_id,
                        trade_time=trade_time,
                        is_buyer_maker=is_buyer_maker
                    )

                    callback = self._callbacks.get(symbol.upper())
                    if callback:
                        try:
                            result = callback(price_update)
                            # Support both async and sync callbacks
                            if asyncio.iscoroutine(result):
                                asyncio.create_task(result)
                        except Exception as e:
                            logger.error(f"Error in price callback for {symbol}: {e}")

            # Handle subscription response
            elif "id" in data and "result" in data:
                logger.debug(_c(_COLOR_DEBUG, f"Subscription response: {data}"))

        except json.JSONDecodeError as e:
            logger.error(_c(_COLOR_ERROR, f"Failed to parse WebSocket message: {e}"))
        except Exception as e:
            logger.error(_c(_COLOR_ERROR, f"Error handling message: {e}"))

    async def subscribe(self, symbol: str, callback: Callable[[PriceUpdate], None]):
        """
        Subscribe to price updates for a symbol.
        Only one callback per symbol is supported (last one wins).
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            callback: Function to call when price updates
        """
        symbol_upper = symbol.upper()
        
        async with self._lock:
            is_new_symbol = symbol_upper not in self._subscribed_symbols
            self._subscribed_symbols.add(symbol_upper)
            self._callbacks[symbol_upper] = callback

        if is_new_symbol:
            logger.info(_c(_COLOR_INFO, f"Subscribed to {symbol_upper}"))
            # Send live subscribe message instead of reconnecting
            if self._websocket:
                await self._send_subscribe([symbol_upper])

    async def unsubscribe(self, symbol: str):
        """Unsubscribe from price updates for a symbol"""
        symbol_upper = symbol.upper()
        
        async with self._lock:
            if symbol_upper in self._subscribed_symbols:
                self._subscribed_symbols.discard(symbol_upper)
                self._callbacks.pop(symbol_upper, None)
                logger.info(_c(_COLOR_INFO, f"Unsubscribed from {symbol_upper}"))

                # Send live unsubscribe message instead of reconnecting
                if self._websocket:
                    await self._send_unsubscribe([symbol_upper])

    def is_subscribed(self, symbol: str) -> bool:
        """Check if a symbol is currently subscribed"""
        return symbol.upper() in self._subscribed_symbols

    async def stop(self):
        """Stop the WebSocket client"""
        self._running = False
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
        logger.info(_c(_COLOR_INFO, "Binance WebSocket client stopped"))


# Global WebSocket client instance
_binance_ws_client: BinanceWebSocketClient | None = None


def get_binance_ws_client() -> BinanceWebSocketClient:
    """Get or create the global Binance WebSocket client"""
    global _binance_ws_client
    if _binance_ws_client is None:
        _binance_ws_client = BinanceWebSocketClient()
    return _binance_ws_client


async def start_binance_ws_client():
    """Start the global Binance WebSocket client"""
    client = get_binance_ws_client()
    asyncio.create_task(client.start())


async def stop_binance_ws_client():
    """Stop the global Binance WebSocket client"""
    global _binance_ws_client
    if _binance_ws_client:
        await _binance_ws_client.stop()
        _binance_ws_client = None