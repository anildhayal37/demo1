"""
FastAPI server — runs the HFT agent in the background and streams
all state to connected browser clients over WebSocket.
"""
import asyncio
import json
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import Config
from data_feed import DataFeed
from portfolio import Portfolio
from agent import HFTAgent

# ── shared state ──────────────────────────────────────────────────────────────

_feed: Optional[DataFeed] = None
_portfolio: Optional[Portfolio] = None
_agent: Optional[HFTAgent] = None
_config: Optional[Config] = None
_start_time: float = 0.0
_agent_task: Optional[asyncio.Task] = None
_feed_task: Optional[asyncio.Task] = None
_running: bool = False

# price history for charts: {symbol: deque of {time, open, high, low, close, volume}}
_candles: dict[str, deque] = {}
_candle_interval: int = 5          # seconds per candle
_last_candle_time: dict[str, float] = {}
_current_candle: dict[str, dict] = {}

_ws_clients: list[WebSocket] = []


# ── candle builder ────────────────────────────────────────────────────────────

def _update_candle(symbol: str, price: float, ts: float):
    interval = _candle_interval
    bucket = int(ts // interval) * interval

    if symbol not in _current_candle or _last_candle_time.get(symbol, 0) != bucket:
        # close previous candle
        if symbol in _current_candle:
            _candles[symbol].append(dict(_current_candle[symbol]))
        _current_candle[symbol] = {
            "time": bucket,
            "open": price, "high": price, "low": price, "close": price,
        }
        _last_candle_time[symbol] = bucket
    else:
        c = _current_candle[symbol]
        c["high"] = max(c["high"], price)
        c["low"] = min(c["low"], price)
        c["close"] = price


# ── broadcast loop ────────────────────────────────────────────────────────────

async def _broadcast_loop():
    while _running:
        if _ws_clients and _feed and _portfolio:
            payload = _build_payload()
            msg = json.dumps(payload)
            dead = []
            for ws in _ws_clients:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                _ws_clients.remove(ws)
        await asyncio.sleep(0.25)


def _build_payload() -> dict:
    prices = _feed.get_all_prices()
    stats = _portfolio.get_stats()

    # update candles from current prices
    now = time.time()
    for sym, price in prices.items():
        _update_candle(sym, price, now)

    # build candle data per symbol (history + live candle)
    chart_data = {}
    for sym in (_config.symbols if _config else []):
        history = list(_candles.get(sym, []))
        live = _current_candle.get(sym)
        if live:
            history = history + [dict(live)]
        chart_data[sym] = history[-300:]  # last 300 candles

    positions = []
    for pos in _portfolio.get_open_positions():
        cur = prices.get(pos.symbol, pos.entry_price)
        upnl = (cur - pos.entry_price) * pos.qty if pos.side == "long" else (pos.entry_price - cur) * pos.qty
        positions.append({
            "symbol": pos.symbol.replace("USDT", ""),
            "side": pos.side,
            "entry_price": pos.entry_price,
            "current_price": cur,
            "qty": pos.qty,
            "upnl": upnl,
            "take_profit": pos.take_profit,
            "stop_loss": pos.stop_loss,
            "trade_id": pos.trade_id,
        })

    trades = []
    for t in _portfolio.get_trade_history(30):
        trades.append({
            "trade_id": t.trade_id,
            "symbol": t.symbol.replace("USDT", ""),
            "side": t.side,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "pnl": t.pnl,
            "exit_reason": t.exit_reason,
            "duration_ms": t.duration_ms,
            "timestamp": t.timestamp,
        })

    equity = _portfolio.get_total_equity(prices)
    rpnl = _portfolio.get_realized_pnl()

    return {
        "type": "state",
        "ts": now,
        "prices": {s.replace("USDT", ""): v for s, v in prices.items()},
        "chart_data": {s.replace("USDT", ""): v for s, v in chart_data.items()},
        "portfolio": {
            "cash": _portfolio.cash_balance,
            "equity": equity,
            "realized_pnl": rpnl,
            "unrealized_pnl": _portfolio.get_unrealized_pnl(prices),
            "initial_balance": _config.initial_balance if _config else 100000,
        },
        "stats": stats,
        "positions": positions,
        "trades": trades,
        "log": list(_agent.agent_log)[:20] if _agent else [],
        "config": {
            "strategy": _config.strategy if _config else "",
            "symbols": [s.replace("USDT", "") for s in (_config.symbols if _config else [])],
            "trade_size": _config.trade_size_usd if _config else 0,
            "uptime": int(now - _start_time),
        },
        "running": _running,
    }


# ── agent lifecycle ───────────────────────────────────────────────────────────

async def _start_agent(cfg: Config):
    global _feed, _portfolio, _agent, _config, _start_time, _running
    global _agent_task, _feed_task, _candles, _last_candle_time, _current_candle

    _config = cfg
    _feed = DataFeed(cfg)
    _portfolio = Portfolio(cfg)
    _agent = HFTAgent(cfg, _feed, _portfolio)
    _candles = {s: deque(maxlen=500) for s in cfg.symbols}
    _last_candle_time = {}
    _current_candle = {}
    _start_time = time.time()
    _running = True

    _feed_task = asyncio.create_task(_feed.start())
    _agent_task = asyncio.create_task(_agent.run())
    asyncio.create_task(_broadcast_loop())


async def _stop_agent():
    global _running
    _running = False
    if _agent:
        _agent.stop()
    if _feed:
        _feed.stop()
    if _agent_task:
        _agent_task.cancel()
    if _feed_task:
        _feed_task.cancel()


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await _stop_agent()


app = FastAPI(lifespan=lifespan)

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text())


@app.post("/api/start")
async def api_start(body: dict):
    global _running
    if _running:
        await _stop_agent()
        await asyncio.sleep(0.5)

    cfg = Config()
    cfg.initial_balance = float(body.get("balance", 100_000))
    raw_symbols = body.get("symbols", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    cfg.symbols = [s.upper() if s.endswith("USDT") else s.upper() + "USDT" for s in raw_symbols]
    cfg.strategy = body.get("strategy", "momentum")
    cfg.trade_size_usd = float(body.get("trade_size", 2_000))
    cfg.take_profit_pct = float(body.get("take_profit", 0.004))
    cfg.stop_loss_pct = float(body.get("stop_loss", 0.002))
    cfg.tick_interval_ms = int(body.get("tick_ms", 250))
    cfg.max_open_positions = int(body.get("max_positions", 5))

    await _start_agent(cfg)
    return {"status": "started"}


@app.post("/api/stop")
async def api_stop():
    await _stop_agent()
    return {"status": "stopped"}


@app.get("/api/status")
async def api_status():
    if not _running or not _portfolio or not _feed:
        return {"running": False}
    return {"running": True, **_build_payload()}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")
