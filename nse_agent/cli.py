"""Command-line interface for the NSE stock analysis agent."""
from __future__ import annotations

import argparse
import json

from .agent import NSEAgent
from .config import DISCLAIMER, AgentConfig


def _fmt_inr(x: float) -> str:
    return f"Rs.{x:,.0f}"


def print_investment(picks: list[dict], capital: float) -> None:
    print("\n" + "=" * 78)
    print(f"  INVESTMENT PICKS (capital: {_fmt_inr(capital)})")
    print("=" * 78)
    for i, p in enumerate(picks, 1):
        f = p["factors"]
        print(f"\n{i}. {p['symbol']}  —  {p['rating']}  (score {p['score']}/100)")
        print(f"   Price {_fmt_inr(p['close'])} | RSI {f['rsi']} | ADX {f['adx']} | "
              f"3m {f['ret_3m_pct']:+.1f}% | 6m {f['ret_6m_pct']:+.1f}%")
        print(f"   BUY ~{p['suggested_quantity']} shares "
              f"(~{_fmt_inr(p['approx_invest_inr'])}, "
              f"allocation {_fmt_inr(p['suggested_allocation_inr'])})")
        if p.get("news_sentiment") is not None:
            mood = ("positive" if p["news_sentiment"] > 0.1 else
                    "negative" if p["news_sentiment"] < -0.1 else "neutral")
            print(f"   News sentiment: {mood} ({p['news_sentiment']:+.2f})")
        for h in p.get("headlines", [])[:3]:
            print(f"     - {h}")


def print_intraday(signals: list[dict], capital: float) -> None:
    print("\n" + "=" * 78)
    print(f"  INTRADAY SIGNALS (capital: {_fmt_inr(capital)}, 2% risk per trade)")
    print("=" * 78)
    if not signals:
        print("\n  No high-confluence setups right now. Best signals appear during "
              "market hours (9:15-15:30 IST), especially after the first 30 minutes.")
    for i, s in enumerate(signals, 1):
        pos = s["position"]
        print(f"\n{i}. {s['symbol']}  —  {s['side']}  [{s['strategy']}]  "
              f"confidence {s['confidence']:.0%}")
        print(f"   Entry {_fmt_inr(s['entry'])} | Stop-loss {_fmt_inr(s['stop_loss'])} "
              f"| Target {_fmt_inr(s['target'])}")
        print(f"   {s['side']} {pos['quantity']} shares = {_fmt_inr(pos['invest_amount'])} "
              f"| max loss {_fmt_inr(pos['risk_amount'])} "
              f"| potential profit {_fmt_inr(pos['potential_profit'])}"
              + (f" ({pos['note']})" if pos['note'] else ""))
        print(f"   Why: {s['reason']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="nse_agent",
        description="AI agent that scans Nifty 500 stocks for investment picks "
                    "and intraday signals with position sizing.",
    )
    ap.add_argument("--mode", choices=["invest", "intraday", "both"], default="both")
    ap.add_argument("--capital", type=float, default=100_000,
                    help="Your capital in INR (default 100000)")
    ap.add_argument("--top", type=int, default=10, help="Number of picks to show")
    ap.add_argument("--limit", type=int, default=None,
                    help="Scan only the first N universe symbols (faster test runs)")
    ap.add_argument("--json", action="store_true", help="Emit raw JSON report")
    ap.add_argument("--ai", action="store_true",
                    help="Add a Claude-written analyst brief (needs ANTHROPIC_API_KEY)")
    args = ap.parse_args(argv)

    cfg = AgentConfig(capital=args.capital, top_n=args.top,
                      universe_size=args.limit, use_ai_analyst=args.ai)
    agent = NSEAgent(cfg)
    report = agent.run(mode=args.mode)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        if "investment_picks" in report:
            print_investment(report["investment_picks"], cfg.capital)
        if "intraday_signals" in report:
            print_intraday(report["intraday_signals"], cfg.capital)

    if args.ai:
        from . import ai_analyst
        print("\n" + "=" * 78 + "\n  AI ANALYST BRIEF\n" + "=" * 78)
        print(ai_analyst.analyze(report))

    print("\n" + "-" * 78)
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
