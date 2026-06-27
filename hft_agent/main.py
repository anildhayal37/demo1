#!/usr/bin/env python3
"""
Crypto HFT Paper Trading Agent
Usage: python main.py [--balance 100000] [--strategy momentum|mean_reversion] [--symbols BTC ETH SOL]
"""
import argparse
import asyncio
import time

from config import Config
from data_feed import DataFeed
from portfolio import Portfolio
from agent import HFTAgent
from dashboard import Dashboard


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Crypto HFT Paper Trader")
    parser.add_argument("--balance", type=float, default=100_000.0, help="Starting cash balance in USD")
    parser.add_argument(
        "--symbols", nargs="+",
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        help="Trading symbols (e.g. BTCUSDT ETHUSDT SOLUSDT)",
    )
    parser.add_argument(
        "--strategy", choices=["momentum", "mean_reversion", "spread"],
        default="momentum", help="Trading strategy",
    )
    parser.add_argument("--trade-size", type=float, default=2_000.0, help="USD notional per trade")
    parser.add_argument("--take-profit", type=float, default=0.004, help="Take profit % (0.004 = 0.4%%)")
    parser.add_argument("--stop-loss", type=float, default=0.002, help="Stop loss % (0.002 = 0.2%%)")
    parser.add_argument("--tick-ms", type=int, default=250, help="Agent tick interval in milliseconds")
    parser.add_argument("--max-positions", type=int, default=5, help="Max simultaneous open positions")
    args = parser.parse_args()

    cfg = Config()
    cfg.initial_balance = args.balance
    cfg.symbols = [s.upper() for s in args.symbols]
    cfg.strategy = args.strategy
    cfg.trade_size_usd = args.trade_size
    cfg.take_profit_pct = args.take_profit
    cfg.stop_loss_pct = args.stop_loss
    cfg.tick_interval_ms = args.tick_ms
    cfg.max_open_positions = args.max_positions
    return cfg


async def main():
    config = parse_args()
    start_time = time.time()

    print(f"\n  Crypto HFT Paper Trader")
    print(f"  Balance:  ${config.initial_balance:,.0f}")
    print(f"  Strategy: {config.strategy}")
    print(f"  Symbols:  {', '.join(config.symbols)}")
    print(f"  Tick:     {config.tick_interval_ms}ms")
    print(f"\n  Connecting to Binance feed...\n")

    feed = DataFeed(config)
    portfolio = Portfolio(config)
    agent = HFTAgent(config, feed, portfolio)
    dashboard = Dashboard(config, feed, portfolio, agent.agent_log, start_time)

    try:
        await asyncio.gather(
            feed.start(),
            agent.run(),
            dashboard.run(),
        )
    except asyncio.CancelledError:
        pass


def print_final_stats(portfolio: Portfolio):
    stats = portfolio.get_stats()
    print("\n" + "=" * 50)
    print("  FINAL PORTFOLIO SUMMARY")
    print("=" * 50)
    print(f"  Cash Balance:   ${portfolio.cash_balance:>12,.2f}")
    print(f"  Realized P&L:   ${portfolio.get_realized_pnl():>+12,.2f}")
    print(f"  Total Trades:   {stats['total_trades']}")
    print(f"  Win Rate:       {stats['win_rate']:.1f}%")
    print(f"  Avg P&L/Trade:  ${stats['avg_pnl']:>+.2f}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    portfolio_ref = None
    try:
        config = parse_args()
        start_time = time.time()
        feed = DataFeed(config)
        portfolio_ref = Portfolio(config)
        agent = HFTAgent(config, feed, portfolio_ref)
        dashboard = Dashboard(config, feed, portfolio_ref, agent.agent_log, start_time)
        asyncio.run(
            asyncio.gather(feed.start(), agent.run(), dashboard.run())
        )
    except KeyboardInterrupt:
        if portfolio_ref:
            print_final_stats(portfolio_ref)
