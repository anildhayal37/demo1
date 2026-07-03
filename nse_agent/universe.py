"""Nifty 500 universe loader.

Pulls the official constituent list from NSE's archive CSV. If that is
unreachable (NSE blocks some networks), falls back to a bundled list of the
largest Nifty constituents so the agent still works offline.
"""
from __future__ import annotations

import csv
import io
import urllib.request

NIFTY500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"

# Fallback: Nifty 100 heavyweights (symbol only; ".NS" suffix added for Yahoo).
FALLBACK_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "BHARTIARTL", "SBIN",
    "LICI", "HINDUNILVR", "ITC", "LT", "BAJFINANCE", "HCLTECH", "MARUTI",
    "SUNPHARMA", "KOTAKBANK", "AXISBANK", "ULTRACEMCO", "NTPC", "TITAN",
    "ONGC", "ADANIENT", "ADANIPORTS", "WIPRO", "POWERGRID", "M&M", "TATAMOTORS",
    "TATASTEEL", "COALINDIA", "BAJAJFINSV", "NESTLEIND", "ASIANPAINT",
    "JSWSTEEL", "GRASIM", "HINDALCO", "SBILIFE", "HDFCLIFE", "DRREDDY",
    "TECHM", "CIPLA", "EICHERMOT", "BRITANNIA", "INDUSINDBK", "DIVISLAB",
    "APOLLOHOSP", "BAJAJ-AUTO", "TATACONSUM", "HEROMOTOCO", "UPL", "BPCL",
    "SHRIRAMFIN", "VEDL", "GODREJCP", "PIDILITIND", "SIEMENS", "DLF",
    "AMBUJACEM", "HAVELLS", "DABUR", "IOC", "GAIL", "ZOMATO", "DMART",
    "BEL", "HAL", "TRENT", "VBL", "PFC", "RECLTD", "IRFC", "JIOFIN",
    "ADANIGREEN", "ADANIPOWER", "TATAPOWER", "LODHA", "NAUKRI", "PNB",
    "BANKBARODA", "CANBK", "UNIONBANK", "IDBI", "CHOLAFIN", "MUTHOOTFIN",
    "BAJAJHLDNG", "ICICIPRULI", "ICICIGI", "SBICARD", "LTIM", "PERSISTENT",
    "COFORGE", "MPHASIS", "OFSS", "POLYCAB", "CGPOWER", "ABB", "BHEL",
    "CUMMINSIND", "ASHOKLEY", "TVSMOTOR", "MOTHERSON", "BOSCHLTD", "MRF",
]


def fetch_nifty500(limit: int | None = None, timeout: int = 20) -> list[str]:
    """Return NSE symbols (without suffix). Falls back to a bundled list."""
    try:
        req = urllib.request.Request(
            NIFTY500_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "text/csv,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        symbols = [r["Symbol"].strip() for r in rows if r.get("Symbol")]
        if len(symbols) < 100:  # sanity check — bad/partial response
            raise ValueError("suspiciously short constituent list")
        source = "NSE archive (live)"
    except Exception:
        symbols = list(FALLBACK_SYMBOLS)
        source = "bundled fallback list"
    if limit:
        symbols = symbols[:limit]
    print(f"[universe] {len(symbols)} symbols loaded from {source}")
    return symbols


def to_yahoo(symbol: str) -> str:
    """NSE symbol -> Yahoo Finance ticker."""
    return f"{symbol}.NS"
