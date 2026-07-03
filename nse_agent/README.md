# NSE Stock Analysis Agent

An AI agent that scans the **Nifty 500** and answers three questions:

1. **Where to invest** — ranks every stock with a multi-factor quant score
   (trend, momentum, 52-week-high proximity, volatility, volume, fundamentals,
   news sentiment) and rates it STRONG BUY / BUY / HOLD / AVOID.
2. **What to trade intraday** — generates signals from the strategy families
   institutional and prop desks actually use:
   - **Opening Range Breakout (ORB)** — break of the first 30-minute range on
     above-average volume, confirmed by the daily trend.
   - **VWAP strategies** — mean reversion when price is stretched from VWAP in
     a range-bound market; trend continuation when price holds above a rising
     VWAP with strong ADX. (VWAP is the benchmark institutions execute against.)
   - **Momentum with Supertrend/ADX confirmation** — ride strength only when
     the higher-timeframe trend agrees.
3. **How much to buy/sell** — position sizing with the professional
   **2%-risk rule**: quantity = (capital × 2%) ÷ distance to stop-loss, capped
   at 20% of capital per position. Every signal comes with entry, stop-loss,
   target (1:2 reward:risk), share quantity, rupee amount, max loss, and
   potential profit.

News headlines are pulled from Google News RSS per stock and scored with a
built-in finance sentiment lexicon — no API keys needed.

## Install

```bash
pip install -r nse_agent/requirements.txt
```

## Usage

```bash
# Full scan: investment picks + intraday signals for Rs.2,00,000 capital
python -m nse_agent --capital 200000

# Investment picks only, top 15
python -m nse_agent --mode invest --top 15 --capital 500000

# Intraday signals only (run during market hours 9:15–15:30 IST for best results)
python -m nse_agent --mode intraday --capital 100000

# Quick test on the first 50 symbols
python -m nse_agent --limit 50

# Raw JSON output (for piping into other tools)
python -m nse_agent --json > scan.json

# Add a Claude-written analyst brief on top of the quant scan
export ANTHROPIC_API_KEY=sk-ant-...   # then:
python -m nse_agent --ai
```

## Example output

```
1. TRENT  —  STRONG BUY  (score 81.4/100)
   Price Rs.6,240 | RSI 62.1 | ADX 31.4 | 3m +18.2% | 6m +42.7%
   BUY ~4 shares (~Rs.24,960, allocation Rs.25,110)
   News sentiment: positive (+0.34)

1. RELIANCE  —  BUY  [ORB breakout]  confidence 85%
   Entry Rs.2,980 | Stop-loss Rs.2,952 | Target Rs.3,036
   BUY 71 shares = Rs.211,580 | max loss Rs.1,988 | potential profit Rs.3,976
   Why: Broke above 30-min opening range high 2975.20 on 1.6x volume with daily uptrend
```

## How it works

```
Nifty 500 list (NSE archive CSV, bundled fallback)
        │
        ▼
Daily OHLCV (yfinance, batched)  ──►  Multi-factor scoring (all 500)
        │                                     │ top ~20 shortlist
        ▼                                     ▼
5-min intraday bars (top 50)          Fundamentals + news enrichment, rescore
        │                                     │
        ▼                                     ▼
ORB / VWAP / momentum signals         Score-weighted allocation
        │                                     │
        └──────► 2%-rule position sizing ◄────┘
                        │
                        ▼
              Report (console / JSON / AI analyst brief)
```

## ⚠️ Disclaimer

This tool is for **education and research only**. It is **not investment
advice**. Signals are generated from public data with simple models; they can
be wrong, stale, or based on bad data. Intraday trading in particular loses
money for most retail participants. Consult a SEBI-registered investment
adviser and never risk money you cannot afford to lose.
