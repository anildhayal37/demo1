import asyncio
import time
from collections import deque

from config import Config
from data_feed import DataFeed
from portfolio import Portfolio
from strategies import get_strategy


class HFTAgent:
    def __init__(self, config: Config, feed: DataFeed, portfolio: Portfolio):
        self.config = config
        self.feed = feed
        self.portfolio = portfolio
        self.strategy = get_strategy(config)
        self.agent_log: deque[str] = deque(maxlen=50)
        self._running = True
        self._start_time = time.time()
        self._tick_count = 0

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.agent_log.appendleft(f"[{ts}] {msg}")

    async def run(self):
        self._log(f"Agent started | strategy={self.config.strategy} | balance=${self.config.initial_balance:,.0f}")
        interval = self.config.tick_interval_ms / 1000.0
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                self._log(f"Tick error: {e}")
            await asyncio.sleep(interval)

    async def _tick(self):
        self._tick_count += 1
        current_prices = self.feed.get_all_prices()
        if not current_prices:
            return

        closed = self.portfolio.check_exits(current_prices)
        for trade in closed:
            sign = "+" if trade.pnl >= 0 else ""
            self._log(
                f"CLOSED {trade.symbol} {trade.side.upper()} "
                f"@ ${trade.exit_price:,.2f} | P&L: {sign}${trade.pnl:.2f} | {trade.exit_reason}"
            )

        for symbol in self.config.symbols:
            if not self.feed.is_ready(symbol):
                continue

            price = self.feed.get_price(symbol)
            if price is None:
                continue

            prices = self.feed.get_price_history(symbol)
            signal = self.strategy.evaluate(symbol, prices, self.portfolio)

            if signal.action == "buy":
                pos = self.portfolio.open_position(symbol, "long", price)
                if pos:
                    self._log(
                        f"BUY  {symbol} @ ${price:,.2f} | "
                        f"TP=${pos.take_profit:,.2f} SL=${pos.stop_loss:,.2f} | {signal.reason}"
                    )
            elif signal.action == "sell":
                open_pos = {p.symbol: p for p in self.portfolio.get_open_positions()}
                if symbol in open_pos and open_pos[symbol].side == "long":
                    trade = self.portfolio.close_position(symbol, price, "signal")
                    if trade:
                        sign = "+" if trade.pnl >= 0 else ""
                        self._log(
                            f"SELL {symbol} @ ${price:,.2f} | P&L: {sign}${trade.pnl:.2f} | {signal.reason}"
                        )
                elif symbol not in open_pos:
                    pos = self.portfolio.open_position(symbol, "short", price)
                    if pos:
                        self._log(
                            f"SHORT {symbol} @ ${price:,.2f} | "
                            f"TP=${pos.take_profit:,.2f} SL=${pos.stop_loss:,.2f} | {signal.reason}"
                        )

    def stop(self):
        self._running = False
