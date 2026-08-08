"""
Local web server for the Crypto Advisor — standard library only.

Run:  python3 -m crypto_advisor      (then open http://localhost:8000)
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import indicators
from .feed import Feed, SYMBOLS, INTERVAL_SECONDS
from .portfolio import Portfolio

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# single shared instances for the life of the process
FEED = Feed()
PORTFOLIO = Portfolio()


def _build_snapshot(symbol: str, interval: str, limit: int) -> dict:
    candles, source = FEED.get_candles(symbol, interval, limit)
    closes = [c["close"] for c in candles]
    signal = indicators.compute_signal(closes)

    # value the portfolio using fresh prices for every held symbol + this one
    held = list(PORTFOLIO.holdings.keys())
    price_syms = set(held) | {symbol.upper()}
    prices = FEED.prices_for(price_syms)
    if candles:
        prices[symbol.upper()] = candles[-1]["close"]
    port = PORTFOLIO.snapshot(prices)

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "source": source,
        "price": candles[-1]["close"] if candles else None,
        "candles": candles,
        "signal": signal,
        "portfolio": port,
    }


class Handler(BaseHTTPRequestHandler):
    # quieter logging
    def log_message(self, fmt, *args):
        pass

    # ── helpers ──────────────────────────────────────────────────────────────
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode() or "{}")
        except Exception:
            return {}

    # ── routing ──────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            return self._file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        if path == "/app.js":
            return self._file(os.path.join(STATIC_DIR, "app.js"), "application/javascript")
        if path == "/style.css":
            return self._file(os.path.join(STATIC_DIR, "style.css"), "text/css")

        if path == "/api/symbols":
            return self._json({
                "symbols": [{"symbol": s, "label": d["label"]} for s, d in SYMBOLS.items()],
                "intervals": list(INTERVAL_SECONDS.keys()),
            })

        if path == "/api/snapshot":
            symbol = (q.get("symbol", ["BTCUSDT"])[0]).upper()
            interval = q.get("interval", ["1m"])[0]
            limit = int(q.get("limit", ["200"])[0])
            if symbol not in SYMBOLS:
                return self._json({"error": "unknown symbol"}, 400)
            return self._json(_build_snapshot(symbol, interval, limit))

        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/buy":
            symbol = (body.get("symbol") or "").upper()
            usd = float(body.get("usd") or 0)
            price = FEED.get_price(symbol) or 0.0
            return self._json(PORTFOLIO.buy(symbol, usd, price))

        if path == "/api/sell":
            symbol = (body.get("symbol") or "").upper()
            price = FEED.get_price(symbol) or 0.0
            usd = body.get("usd")
            pct = body.get("pct")
            return self._json(PORTFOLIO.sell(
                symbol, price,
                usd=float(usd) if usd is not None else None,
                pct=float(pct) if pct is not None else None,
            ))

        if path == "/api/reset":
            PORTFOLIO.reset()
            return self._json({"ok": True})

        self.send_error(404)


def serve(host: str = "127.0.0.1", port: int = 8000):
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("\n  Crypto Advisor — local paper-trading dashboard")
    print(f"  Starting balance: ${PORTFOLIO.start_cash:,.0f} (paper money)")
    print(f"  Open your browser at:  http://{host}:{port}\n")
    print("  Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped. Your paper portfolio resets on restart.\n")
        httpd.shutdown()
