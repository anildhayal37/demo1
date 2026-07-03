"""News fetching and sentiment scoring.

Headlines come from Google News RSS (no API key needed). Sentiment uses a
built-in finance lexicon so there is nothing to download at runtime.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

POSITIVE = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "record", "profit",
    "profits", "gain", "gains", "upgrade", "upgraded", "outperform", "buy",
    "bullish", "growth", "strong", "wins", "win", "order", "orders", "expansion",
    "dividend", "bonus", "buyback", "approval", "approved", "jump", "jumps",
    "soar", "soars", "high", "raises", "raised", "boost", "boosts", "positive",
    "recovery", "rebound", "milestone", "partnership", "contract", "acquires",
}
NEGATIVE = {
    "miss", "misses", "fall", "falls", "drop", "drops", "plunge", "plunges",
    "loss", "losses", "downgrade", "downgraded", "underperform", "sell",
    "bearish", "weak", "decline", "declines", "probe", "investigation", "fraud",
    "penalty", "fine", "fined", "lawsuit", "default", "debt", "layoff",
    "layoffs", "cuts", "cut", "warning", "warns", "crash", "slump", "slumps",
    "negative", "resign", "resigns", "scam", "ban", "banned", "recall", "strike",
}


@dataclass
class NewsResult:
    headlines: list[str] = field(default_factory=list)
    sentiment: float = 0.0  # -1 (very negative) .. +1 (very positive)
    n_articles: int = 0


def _score_text(text: str) -> float:
    words = re.findall(r"[a-z']+", text.lower())
    pos = sum(w in POSITIVE for w in words)
    neg = sum(w in NEGATIVE for w in words)
    total = pos + neg
    return (pos - neg) / total if total else 0.0


def fetch_news(company_query: str, limit: int = 8, timeout: int = 15) -> NewsResult:
    """Fetch recent headlines for a company and compute aggregate sentiment."""
    q = urllib.parse.quote(f"{company_query} NSE stock")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    result = NewsResult()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
        items = root.findall(".//item")[:limit]
        titles = [i.findtext("title", default="") for i in items]
        titles = [t for t in titles if t]
        if not titles:
            return result
        scores = [_score_text(t) for t in titles]
        result.headlines = titles
        result.n_articles = len(titles)
        result.sentiment = sum(scores) / len(scores)
    except Exception:
        pass  # news is a bonus factor; never fail the scan over it
    return result
