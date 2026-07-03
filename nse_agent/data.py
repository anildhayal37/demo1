"""Market data layer (Yahoo Finance via yfinance).

Downloads daily history in batches for the whole universe, plus optional
5-minute intraday bars for intraday signal generation and per-ticker
fundamental snapshots.
"""
from __future__ import annotations

import warnings

import pandas as pd
import yfinance as yf

from .universe import to_yahoo

warnings.filterwarnings("ignore", category=FutureWarning)

BATCH = 50


def fetch_daily(symbols: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Daily OHLCV per NSE symbol. Symbols with no data are dropped."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), BATCH):
        chunk = symbols[i : i + BATCH]
        tickers = [to_yahoo(s) for s in chunk]
        data = yf.download(
            tickers, period=period, interval="1d", group_by="ticker",
            auto_adjust=True, progress=False, threads=True,
        )
        for sym, tkr in zip(chunk, tickers):
            try:
                df = data[tkr] if len(tickers) > 1 else data
            except KeyError:
                continue
            df = df.dropna(subset=["Close"])
            if len(df) >= 60:  # need enough history for indicators
                out[sym] = df
        print(f"[data] daily bars: {min(i + BATCH, len(symbols))}/{len(symbols)} fetched", end="\r")
    print()
    return out


def fetch_intraday(symbols: list[str], interval: str = "5m") -> dict[str, pd.DataFrame]:
    """Recent 5-minute bars (last 5 sessions) for intraday strategies."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), BATCH):
        chunk = symbols[i : i + BATCH]
        tickers = [to_yahoo(s) for s in chunk]
        data = yf.download(
            tickers, period="5d", interval=interval, group_by="ticker",
            auto_adjust=True, progress=False, threads=True,
        )
        for sym, tkr in zip(chunk, tickers):
            try:
                df = data[tkr] if len(tickers) > 1 else data
            except KeyError:
                continue
            df = df.dropna(subset=["Close"])
            if len(df) >= 30:
                out[sym] = df
    return out


def fetch_fundamentals(symbol: str) -> dict:
    """Fundamental snapshot for one symbol (best-effort; may be sparse)."""
    try:
        info = yf.Ticker(to_yahoo(symbol)).info or {}
    except Exception:
        return {}
    return {
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "roe": info.get("returnOnEquity"),
        "debt_to_equity": info.get("debtToEquity"),
        "profit_margin": info.get("profitMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector"),
    }
