import asyncio
import json
import time
from collections import deque

import aiohttp
import numpy as np

from config import Config


class DataFeed:
    def __init__(self, config: Config):
        self.config = config
        self._prices: dict[str, float] = {}
        self._prev_prices: dict[str, float] = {}
        self._buffers: dict[str, deque] = {
            s: deque(maxlen=config.price_buffer_size) for s in config.symbols
        }
        self._last_update: dict[str, float] = {}
        self._running = True
        self._ws_failures = 0
        self._use_rest_fallback = False

    def get_price(self, symbol: str) -> float | None:
        return self._prices.get(symbol)

    def get_prev_price(self, symbol: str) -> float | None:
        return self._prev_prices.get(symbol)

    def get_price_history(self, symbol: str, n: int | None = None) -> np.ndarray:
        buf = self._buffers.get(symbol, deque())
        arr = np.array(list(buf), dtype=float)
        if n is not None and len(arr) > n:
            return arr[-n:]
        return arr

    def get_all_prices(self) -> dict[str, float]:
        return dict(self._prices)

    def is_ready(self, symbol: str, min_ticks: int = 55) -> bool:
        return len(self._buffers.get(symbol, [])) >= min_ticks

    def _update_price(self, symbol: str, price: float):
        self._prev_prices[symbol] = self._prices.get(symbol, price)
        self._prices[symbol] = price
        self._buffers[symbol].append(price)
        self._last_update[symbol] = time.time()

    async def start(self):
        while self._running:
            if self._use_rest_fallback:
                await self._rest_poll_loop()
            else:
                await self._websocket_loop()

    async def _websocket_loop(self):
        streams = "/".join(s.lower() + "@aggTrade" for s in self.config.symbols)
        url = f"{self.config.websocket_url}?streams={streams}"
        try:
            import websockets
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                self._ws_failures = 0
                while self._running:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        msg = json.loads(raw)
                        data = msg.get("data", {})
                        stream = msg.get("stream", "")
                        symbol = stream.split("@")[0].upper()
                        if symbol in self.config.symbols:
                            price = float(data.get("p", 0))
                            if price > 0:
                                self._update_price(symbol, price)
                    except asyncio.TimeoutError:
                        continue
        except Exception as e:
            self._ws_failures += 1
            if self._ws_failures >= 3:
                self._use_rest_fallback = True
            wait = min(2 ** self._ws_failures, 30)
            await asyncio.sleep(wait)

    async def _rest_poll_loop(self):
        async with aiohttp.ClientSession() as session:
            while self._running:
                for symbol in self.config.symbols:
                    try:
                        url = f"{self.config.rest_url}/ticker/price?symbol={symbol}"
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                            data = await resp.json()
                            price = float(data.get("price", 0))
                            if price > 0:
                                self._update_price(symbol, price)
                    except Exception:
                        pass
                await asyncio.sleep(0.5)

    def stop(self):
        self._running = False
