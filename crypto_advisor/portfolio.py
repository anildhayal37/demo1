"""
Paper-trading portfolio.

Tracks a cash balance plus crypto holdings. Buying spends cash for coins at the
current price; selling returns cash and books realized P&L. Nothing here touches
real money — it is a simulator for learning and testing strategies.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

START_CASH = 100_000.0
FEE_PCT = 0.001  # 0.1% taker fee, like a typical exchange, so results stay realistic


class Portfolio:
    def __init__(self, start_cash: float = START_CASH):
        self._lock = threading.Lock()
        self.start_cash = start_cash
        self.cash = start_cash
        # symbol -> {"qty": float, "avg_cost": float}
        self.holdings: Dict[str, dict] = {}
        self.realized_pnl = 0.0
        self.trades: List[dict] = []

    # ── actions ────────────────────────────────────────────────────────────────

    def buy(self, symbol: str, usd: float, price: float) -> dict:
        symbol = symbol.upper()
        with self._lock:
            if price <= 0:
                return {"ok": False, "error": "No live price available."}
            if usd <= 0:
                return {"ok": False, "error": "Enter an amount greater than 0."}
            cost = usd * (1 + FEE_PCT)
            if cost > self.cash + 1e-9:
                return {"ok": False, "error": f"Not enough cash. Available ${self.cash:,.2f}."}

            qty = usd / price
            h = self.holdings.get(symbol)
            if h:
                new_qty = h["qty"] + qty
                h["avg_cost"] = (h["avg_cost"] * h["qty"] + price * qty) / new_qty
                h["qty"] = new_qty
            else:
                self.holdings[symbol] = {"qty": qty, "avg_cost": price}

            self.cash -= cost
            self._record("BUY", symbol, qty, price, 0.0)
            return {"ok": True, "qty": qty, "price": price, "cash": self.cash}

    def sell(self, symbol: str, price: float,
             usd: Optional[float] = None, pct: Optional[float] = None) -> dict:
        """Sell either a USD notional, a percentage of the holding, or all of it."""
        symbol = symbol.upper()
        with self._lock:
            if price <= 0:
                return {"ok": False, "error": "No live price available."}
            h = self.holdings.get(symbol)
            if not h or h["qty"] <= 0:
                return {"ok": False, "error": f"You don't hold any {_short(symbol)}."}

            if pct is not None:
                qty = h["qty"] * max(0.0, min(1.0, pct / 100.0))
            elif usd is not None:
                qty = min(h["qty"], usd / price)
            else:
                qty = h["qty"]  # sell all

            if qty <= 0:
                return {"ok": False, "error": "Nothing to sell."}

            proceeds = qty * price * (1 - FEE_PCT)
            cost_basis = qty * h["avg_cost"]
            pnl = proceeds - cost_basis
            self.cash += proceeds
            self.realized_pnl += pnl
            h["qty"] -= qty
            if h["qty"] <= 1e-12:
                del self.holdings[symbol]

            self._record("SELL", symbol, qty, price, pnl)
            return {"ok": True, "qty": qty, "price": price, "pnl": pnl, "cash": self.cash}

    def reset(self):
        with self._lock:
            self.cash = self.start_cash
            self.holdings = {}
            self.realized_pnl = 0.0
            self.trades = []

    # ── reporting ────────────────────────────────────────────────────────────────

    def snapshot(self, prices: Dict[str, float]) -> dict:
        with self._lock:
            positions = []
            holdings_value = 0.0
            unrealized = 0.0
            for sym, h in self.holdings.items():
                price = prices.get(sym, h["avg_cost"])
                value = h["qty"] * price
                cost = h["qty"] * h["avg_cost"]
                pnl = value - cost
                pnl_pct = (pnl / cost * 100) if cost else 0.0
                holdings_value += value
                unrealized += pnl
                positions.append({
                    "symbol": sym,
                    "short": _short(sym),
                    "qty": h["qty"],
                    "avg_cost": h["avg_cost"],
                    "price": price,
                    "value": value,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                })
            equity = self.cash + holdings_value
            total_pnl = equity - self.start_cash
            return {
                "cash": self.cash,
                "holdings_value": holdings_value,
                "equity": equity,
                "start_cash": self.start_cash,
                "realized_pnl": self.realized_pnl,
                "unrealized_pnl": unrealized,
                "total_pnl": total_pnl,
                "total_pnl_pct": (total_pnl / self.start_cash * 100) if self.start_cash else 0.0,
                "positions": sorted(positions, key=lambda p: -p["value"]),
                "trades": list(reversed(self.trades[-50:])),
            }

    # ── internals ────────────────────────────────────────────────────────────────

    def _record(self, side: str, symbol: str, qty: float, price: float, pnl: float):
        self.trades.append({
            "time": time.time(),
            "side": side,
            "symbol": symbol,
            "short": _short(symbol),
            "qty": qty,
            "price": price,
            "usd": qty * price,
            "pnl": pnl,
        })


def _short(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol
