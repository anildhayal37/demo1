import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from config import Config


@dataclass
class Position:
    symbol: str
    side: str
    entry_price: float
    qty: float
    entry_time: float
    take_profit: float
    stop_loss: float
    trade_id: str


@dataclass
class Trade:
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    fee: float
    duration_ms: float
    exit_reason: str
    timestamp: float


class Portfolio:
    def __init__(self, config: Config):
        self.config = config
        self._cash = config.initial_balance
        self._positions: dict[str, Position] = {}
        self._trade_history: deque[Trade] = deque(maxlen=200)
        self._realized_pnl: float = 0.0
        self._total_trades: int = 0
        self._winning_trades: int = 0

    @property
    def cash_balance(self) -> float:
        return self._cash

    def open_position(self, symbol: str, side: str, price: float) -> Optional[Position]:
        if symbol in self._positions:
            return None
        if len(self._positions) >= self.config.max_open_positions:
            return None
        notional = self.config.trade_size_usd
        fee = notional * self.config.fee_pct
        if self._cash < notional + fee:
            return None

        qty = notional / price
        if side == "long":
            tp = price * (1 + self.config.take_profit_pct)
            sl = price * (1 - self.config.stop_loss_pct)
        else:
            tp = price * (1 - self.config.take_profit_pct)
            sl = price * (1 + self.config.stop_loss_pct)

        self._cash -= notional + fee
        pos = Position(
            symbol=symbol,
            side=side,
            entry_price=price,
            qty=qty,
            entry_time=time.time(),
            take_profit=tp,
            stop_loss=sl,
            trade_id=str(uuid.uuid4())[:8],
        )
        self._positions[symbol] = pos
        return pos

    def close_position(self, symbol: str, exit_price: float, reason: str) -> Optional[Trade]:
        pos = self._positions.pop(symbol, None)
        if pos is None:
            return None

        if pos.side == "long":
            raw_pnl = (exit_price - pos.entry_price) * pos.qty
        else:
            raw_pnl = (pos.entry_price - exit_price) * pos.qty

        notional = pos.entry_price * pos.qty
        fee = (notional + abs(exit_price * pos.qty)) * self.config.fee_pct
        net_pnl = raw_pnl - fee
        self._cash += notional + net_pnl
        self._realized_pnl += net_pnl
        self._total_trades += 1
        if net_pnl > 0:
            self._winning_trades += 1

        trade = Trade(
            trade_id=pos.trade_id,
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            qty=pos.qty,
            pnl=net_pnl,
            fee=fee,
            duration_ms=(time.time() - pos.entry_time) * 1000,
            exit_reason=reason,
            timestamp=time.time(),
        )
        self._trade_history.appendleft(trade)
        return trade

    def check_exits(self, current_prices: dict[str, float]) -> list[Trade]:
        closed = []
        for symbol, pos in list(self._positions.items()):
            price = current_prices.get(symbol)
            if price is None:
                continue
            if pos.side == "long":
                if price >= pos.take_profit:
                    t = self.close_position(symbol, price, "take_profit")
                elif price <= pos.stop_loss:
                    t = self.close_position(symbol, price, "stop_loss")
                else:
                    continue
            else:
                if price <= pos.take_profit:
                    t = self.close_position(symbol, price, "take_profit")
                elif price >= pos.stop_loss:
                    t = self.close_position(symbol, price, "stop_loss")
                else:
                    continue
            if t:
                closed.append(t)
        return closed

    def get_open_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        total = 0.0
        for symbol, pos in self._positions.items():
            price = current_prices.get(symbol)
            if price is None:
                continue
            if pos.side == "long":
                total += (price - pos.entry_price) * pos.qty
            else:
                total += (pos.entry_price - price) * pos.qty
        return total

    def get_realized_pnl(self) -> float:
        return self._realized_pnl

    def get_total_equity(self, current_prices: dict[str, float]) -> float:
        return self._cash + sum(
            pos.entry_price * pos.qty for pos in self._positions.values()
        ) + self.get_unrealized_pnl(current_prices)

    def get_trade_history(self, n: int = 20) -> list[Trade]:
        return list(self._trade_history)[:n]

    def get_stats(self) -> dict:
        win_rate = (self._winning_trades / self._total_trades * 100) if self._total_trades > 0 else 0.0
        trades = list(self._trade_history)
        avg_duration = (
            sum(t.duration_ms for t in trades) / len(trades) if trades else 0.0
        )
        avg_pnl = (
            sum(t.pnl for t in trades) / len(trades) if trades else 0.0
        )
        return {
            "total_trades": self._total_trades,
            "winning_trades": self._winning_trades,
            "win_rate": win_rate,
            "avg_duration_ms": avg_duration,
            "avg_pnl": avg_pnl,
        }
