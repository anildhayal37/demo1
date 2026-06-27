"""
Market data feed.

Pulls real OHLC candles from public exchange REST APIs using only the Python
standard library (urllib). If no exchange is reachable (offline, region-blocked,
or a locked-down sandbox) it transparently falls back to a synthetic price
generator so the app always runs and the buy/sell/P&L flow can be tested.

No API key is required — these are public market-data endpoints.
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.request
from typing import Dict, List, Tuple

# symbol -> human label and a base price used only by the synthetic fallback
SYMBOLS: Dict[str, dict] = {
    "BTCUSDT": {"label": "Bitcoin",  "base": 64000.0},
    "ETHUSDT": {"label": "Ethereum", "base": 3200.0},
    "SOLUSDT": {"label": "Solana",   "base": 150.0},
    "BNBUSDT": {"label": "BNB",      "base": 580.0},
    "XRPUSDT": {"label": "XRP",      "base": 0.52},
    "DOGEUSDT": {"label": "Dogecoin", "base": 0.13},
    "ADAUSDT": {"label": "Cardano",  "base": 0.45},
    "AVAXUSDT": {"label": "Avalanche", "base": 28.0},
}

# interval label -> seconds per candle (for the synthetic generator + spacing)
INTERVAL_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400,
}

# REST providers tried in order. Both speak the Binance kline format.
_PROVIDERS = [
    "https://api.binance.com/api/v3/klines",
    "https://api.binance.us/api/v3/klines",
]


class Feed:
    def __init__(self):
        self._lock = threading.Lock()
        self._last_price: Dict[str, float] = {}
        self._real_failed_at: float = 0.0   # time we last saw a real provider fail
        self._source: str = "starting"

    # ── public API ───────────────────────────────────────────────────────────

    @property
    def source(self) -> str:
        return self._source

    def get_candles(self, symbol: str, interval: str = "1m",
                    limit: int = 200) -> Tuple[List[dict], str]:
        """Return (candles, source). Each candle: {time, open, high, low, close, volume}."""
        symbol = symbol.upper()
        interval = interval if interval in INTERVAL_SECONDS else "1m"
        limit = max(60, min(500, int(limit)))

        candles = None
        source = "synthetic"

        # skip real providers for 60s after a failure to keep the UI snappy offline
        if time.time() - self._real_failed_at > 60:
            candles = self._fetch_real(symbol, interval, limit)
            if candles:
                source = "live"

        if not candles:
            candles = self._synthetic(symbol, interval, limit)
            source = "live" if source == "live" else "synthetic"

        if candles:
            with self._lock:
                self._last_price[symbol] = candles[-1]["close"]
                self._source = source
        return candles, source

    def get_price(self, symbol: str) -> float | None:
        """Latest known price for a symbol (cached from the last candle fetch)."""
        symbol = symbol.upper()
        with self._lock:
            p = self._last_price.get(symbol)
        if p is not None:
            return p
        candles, _ = self.get_candles(symbol, "1m", 60)
        return candles[-1]["close"] if candles else None

    def prices_for(self, symbols) -> Dict[str, float]:
        out = {}
        for s in symbols:
            p = self.get_price(s)
            if p is not None:
                out[s] = p
        return out

    # ── real provider ──────────────────────────────────────────────────────────

    def _fetch_real(self, symbol: str, interval: str, limit: int):
        for url in _PROVIDERS:
            try:
                full = f"{url}?symbol={symbol}&interval={interval}&limit={limit}"
                req = urllib.request.Request(full, headers={"User-Agent": "crypto-advisor/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw = json.loads(resp.read().decode())
                if not isinstance(raw, list) or not raw:
                    continue
                candles = []
                for k in raw:
                    candles.append({
                        "time": int(k[0] // 1000),
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    })
                return candles
            except Exception:
                continue
        self._real_failed_at = time.time()
        return None

    # ── synthetic fallback ──────────────────────────────────────────────────────

    def _synthetic(self, symbol: str, interval: str, limit: int) -> List[dict]:
        """Deterministic-ish random walk so charts look real and prices move
        over time (so unrealized P&L changes between refreshes)."""
        step = INTERVAL_SECONDS[interval]
        base = SYMBOLS.get(symbol, {}).get("base", 100.0)
        seed = sum(ord(c) for c in symbol)
        now = time.time()
        # align the most recent candle to the current interval bucket
        last_bucket = int(now // step) * step
        start = last_bucket - step * (limit - 1)

        candles: List[dict] = []
        prev_close = base
        # a slow global drift tied to wall-clock so the market "moves"
        drift_phase = now / (step * 40.0)
        for i in range(limit):
            t = start + i * step
            # blend a couple of sine waves + deterministic noise
            wave = (0.045 * math.sin(i / 18.0 + seed)
                    + 0.020 * math.sin(i / 5.0 + seed * 0.7)
                    + 0.012 * math.sin(drift_phase + i / 50.0))
            noise = (math.sin((i * 12.9898 + seed * 78.233)) * 43758.5453)
            noise = (noise - math.floor(noise)) - 0.5   # [-0.5, 0.5]
            target = base * (1 + wave) * (1 + 0.004 * noise)
            o = prev_close
            c = target
            hi = max(o, c) * (1 + 0.0015 * abs(noise))
            lo = min(o, c) * (1 - 0.0015 * abs(noise))
            vol = base * (5 + 3 * abs(noise))
            candles.append({
                "time": t,
                "open": round(o, 6),
                "high": round(hi, 6),
                "low": round(lo, 6),
                "close": round(c, 6),
                "volume": round(vol, 2),
            })
            prev_close = c
        return candles
