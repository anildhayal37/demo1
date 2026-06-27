import time
from dataclasses import dataclass

import numpy as np

from config import Config
from portfolio import Portfolio


@dataclass
class Signal:
    symbol: str
    action: str  # "buy" | "sell" | "hold"
    strength: float
    reason: str


def _ema(prices: np.ndarray, window: int) -> np.ndarray:
    alpha = 2.0 / (window + 1)
    ema = np.zeros_like(prices)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = alpha * prices[i] + (1 - alpha) * ema[i - 1]
    return ema


class MomentumScalpingStrategy:
    def __init__(self, config: Config):
        self.config = config
        self._last_signal_time: dict[str, float] = {}
        # Wait at least 2s between any two signals on a symbol (anti-churn).
        self._min_signal_gap = 2.0
        # Don't close a position via signal until it has been held this long;
        # let take-profit / stop-loss do the work instead.
        self._min_hold_seconds = 8.0
        # Only enter when the EMA gap is at least this fraction of price, so we
        # need a *real* trend, not noise. Must clear the round-trip fee too.
        self._entry_threshold = max(0.0008, self.config.fee_pct * 4)
        # Only exit on signal when momentum reverses hard (much bigger wobble).
        self._reversal_threshold = 0.0015

    def evaluate(self, symbol: str, prices: np.ndarray, portfolio: Portfolio) -> Signal:
        now = time.time()
        if now - self._last_signal_time.get(symbol, 0) < self._min_signal_gap:
            return Signal(symbol, "hold", 0.0, "rate_limited")

        w = self.config.momentum_window
        if len(prices) < w + 5:
            return Signal(symbol, "hold", 0.0, "insufficient_data")

        fast = _ema(prices, w // 2)
        slow = _ema(prices, w)
        diff = fast[-1] - slow[-1]
        rel_diff = abs(diff) / slow[-1]
        strength = min(rel_diff / 0.001, 1.0)

        open_pos = {p.symbol: p for p in portfolio.get_open_positions()}

        # Crossover: fast just crossed above slow in last 3 ticks
        recently_crossed_up = fast[-3] < slow[-3] and fast[-1] > slow[-1]
        recently_crossed_down = fast[-3] > slow[-3] and fast[-1] < slow[-1]

        # ENTRY: require a real, fee-beating trend (not a tiny wobble).
        if (recently_crossed_up and symbol not in open_pos
                and rel_diff >= self._entry_threshold):
            self._last_signal_time[symbol] = now
            return Signal(symbol, "buy", strength, "ema_crossover_bullish")

        # EXIT via signal only after a minimum hold AND on a hard reversal.
        # Otherwise we leave the position alone and let TP/SL handle it.
        if symbol in open_pos and open_pos[symbol].side == "long":
            held = now - open_pos[symbol].entry_time
            if held < self._min_hold_seconds:
                return Signal(symbol, "hold", 0.0, "min_hold")
            hard_reversal = (recently_crossed_down or diff < 0) and rel_diff >= self._reversal_threshold
            if hard_reversal:
                self._last_signal_time[symbol] = now
                return Signal(symbol, "sell", strength, "momentum_reversal")

        return Signal(symbol, "hold", 0.0, f"diff={diff:.2f}")


class MeanReversionStrategy:
    def __init__(self, config: Config):
        self.config = config
        self._last_signal_time: dict[str, float] = {}
        self._min_signal_gap = 2.0
        self._min_hold_seconds = 6.0

    def evaluate(self, symbol: str, prices: np.ndarray, portfolio: Portfolio) -> Signal:
        now = time.time()
        if now - self._last_signal_time.get(symbol, 0) < self._min_signal_gap:
            return Signal(symbol, "hold", 0.0, "rate_limited")

        w = self.config.mean_rev_window
        if len(prices) < w:
            return Signal(symbol, "hold", 0.0, "insufficient_data")

        window_prices = prices[-w:]
        mean = np.mean(window_prices)
        std = np.std(window_prices)
        if std == 0:
            return Signal(symbol, "hold", 0.0, "no_variance")

        cv = std / mean
        if cv < 0.0002:
            return Signal(symbol, "hold", 0.0, "market_too_flat")

        z = (prices[-1] - mean) / std
        strength = min(abs(z) / 3.0, 1.0)
        open_pos = {p.symbol: p for p in portfolio.get_open_positions()}

        if z < -1.5 and symbol not in open_pos:
            self._last_signal_time[symbol] = now
            return Signal(symbol, "buy", strength, f"z={z:.2f}_oversold")

        if z > 1.5 and symbol not in open_pos:
            self._last_signal_time[symbol] = now
            return Signal(symbol, "sell", strength, f"z={z:.2f}_overbought")

        if symbol in open_pos:
            pos = open_pos[symbol]
            if now - pos.entry_time < self._min_hold_seconds:
                return Signal(symbol, "hold", 0.0, "min_hold")
            # Exit when price has reverted past the mean (z crosses well through 0).
            if pos.side == "long" and z > 0.5:
                self._last_signal_time[symbol] = now
                return Signal(symbol, "sell", strength, f"z={z:.2f}_mean_reached")
            if pos.side == "short" and z < -0.5:
                self._last_signal_time[symbol] = now
                return Signal(symbol, "sell", strength, f"z={z:.2f}_mean_reached")

        return Signal(symbol, "hold", 0.0, f"z={z:.2f}")


class SpreadTradingStrategy:
    def __init__(self, config: Config):
        self.config = config
        self._pending: dict[str, Signal] = {}
        self._last_signal_time: float = 0
        self._min_signal_gap = 2.0
        self._ratio_buffer: list[float] = []
        self._ratio_window = 60

    def evaluate(self, symbol: str, prices: np.ndarray, portfolio: Portfolio) -> Signal:
        sym_a, sym_b = self.config.spread_symbols

        if symbol in self._pending:
            sig = self._pending.pop(symbol)
            return sig

        if symbol != sym_a:
            return Signal(symbol, "hold", 0.0, "not_spread_symbol")

        now = time.time()
        if now - self._last_signal_time < self._min_signal_gap:
            return Signal(symbol, "hold", 0.0, "rate_limited")

        return Signal(symbol, "hold", 0.0, "spread_needs_both_prices")


def get_strategy(config: Config):
    strategies = {
        "momentum": MomentumScalpingStrategy,
        "mean_reversion": MeanReversionStrategy,
        "spread": SpreadTradingStrategy,
    }
    cls = strategies.get(config.strategy, MomentumScalpingStrategy)
    return cls(config)
