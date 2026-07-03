"""Signal generation.

Two layers:

1. Investment scoring (positional/swing): a multi-factor composite of the
   kind quant funds run — trend, momentum, volatility, volume, 52-week-high
   proximity, fundamentals and news sentiment.

2. Intraday signals: the strategy families used by institutional and prop
   desks —
   - Opening Range Breakout (ORB): trade the break of the first 15/30 min range.
   - VWAP mean reversion / VWAP trend: institutions execute around VWAP, so
     price stretched far from VWAP tends to revert; price holding above VWAP
     with volume confirms trend.
   - Momentum + Supertrend/ADX confirmation: only trade breakouts when the
     trend is strong enough to follow through.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ta


# --------------------------------------------------------------------------
# Investment (positional) scoring
# --------------------------------------------------------------------------

@dataclass
class StockScore:
    symbol: str
    close: float
    score: float                      # 0..100 composite
    rating: str                       # STRONG BUY / BUY / HOLD / AVOID
    factors: dict = field(default_factory=dict)
    news_sentiment: float = 0.0
    headlines: list[str] = field(default_factory=list)


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def score_stock(symbol: str, df: pd.DataFrame, fundamentals: dict | None = None,
                news_sentiment: float = 0.0, headlines: list[str] | None = None) -> StockScore:
    close = df["Close"]
    last = float(close.iloc[-1])

    ema50 = ta.ema(close, 50).iloc[-1]
    ema200 = ta.ema(close, 200).iloc[-1] if len(close) >= 200 else ta.ema(close, len(close) // 2).iloc[-1]
    rsi14 = float(ta.rsi(close).iloc[-1])
    _, _, macd_hist = ta.macd(close)
    adx14 = float(ta.adx(df).iloc[-1])

    # --- factor 1: trend (30%) — price above rising 50/200 EMA, golden cross
    trend = 0.0
    trend += 0.4 if last > ema50 else 0.0
    trend += 0.3 if last > ema200 else 0.0
    trend += 0.3 if ema50 > ema200 else 0.0

    # --- factor 2: momentum (25%) — 3m/6m returns, MACD histogram, RSI zone
    ret_3m = last / float(close.iloc[-63]) - 1 if len(close) > 63 else 0.0
    ret_6m = last / float(close.iloc[-126]) - 1 if len(close) > 126 else ret_3m
    momentum = _clip01(0.5 + ret_3m) * 0.4 + _clip01(0.5 + ret_6m) * 0.3
    momentum += 0.15 if float(macd_hist.iloc[-1]) > 0 else 0.0
    momentum += 0.15 if 45 <= rsi14 <= 70 else 0.0  # healthy, not overbought

    # --- factor 3: 52-week-high proximity (10%) — leaders make new highs
    hi52 = float(close.tail(252).max())
    proximity = _clip01(1 - (hi52 - last) / hi52 / 0.25)  # within 25% of high

    # --- factor 4: volatility & liquidity (10%) — prefer orderly movers
    daily_ret = close.pct_change().dropna()
    ann_vol = float(daily_ret.std() * np.sqrt(252)) if len(daily_ret) else 1.0
    vol_score = _clip01(1 - (ann_vol - 0.20) / 0.40)  # sweet spot ~20-35%
    vol_trend = float(df["Volume"].tail(20).mean() / max(df["Volume"].tail(60).mean(), 1))
    volume_score = _clip01(vol_trend / 1.5)

    # --- factor 5: fundamentals (15%)
    f = fundamentals or {}
    fund = 0.5  # neutral when unknown
    checks = []
    if f.get("pe") is not None:
        checks.append(1.0 if 0 < f["pe"] < 40 else 0.0)
    if f.get("roe") is not None:
        checks.append(1.0 if f["roe"] > 0.15 else 0.3 if f["roe"] > 0 else 0.0)
    if f.get("debt_to_equity") is not None:
        checks.append(1.0 if f["debt_to_equity"] < 100 else 0.3)
    if f.get("earnings_growth") is not None:
        checks.append(1.0 if f["earnings_growth"] > 0.10 else 0.3 if f["earnings_growth"] > 0 else 0.0)
    if checks:
        fund = sum(checks) / len(checks)

    # --- factor 6: news sentiment (10%)
    news = _clip01(0.5 + news_sentiment / 2)

    composite = 100 * (
        0.30 * trend + 0.25 * momentum + 0.10 * proximity
        + 0.05 * vol_score + 0.05 * volume_score + 0.15 * fund + 0.10 * news
    )
    rating = ("STRONG BUY" if composite >= 75 else
              "BUY" if composite >= 60 else
              "HOLD" if composite >= 45 else "AVOID")

    return StockScore(
        symbol=symbol, close=last, score=round(composite, 1), rating=rating,
        factors={
            "trend": round(trend, 2), "momentum": round(momentum, 2),
            "near_52w_high": round(proximity, 2), "volatility": round(ann_vol, 2),
            "fundamentals": round(fund, 2), "rsi": round(rsi14, 1),
            "adx": round(adx14, 1), "ret_3m_pct": round(ret_3m * 100, 1),
            "ret_6m_pct": round(ret_6m * 100, 1),
        },
        news_sentiment=round(news_sentiment, 2),
        headlines=headlines or [],
    )


# --------------------------------------------------------------------------
# Intraday signals
# --------------------------------------------------------------------------

@dataclass
class IntradaySignal:
    symbol: str
    strategy: str
    side: str          # BUY or SELL (sell = short / exit-long zone)
    entry: float
    stop_loss: float
    target: float
    reason: str
    confidence: float  # 0..1


def _last_session(df: pd.DataFrame) -> pd.DataFrame:
    dates = df.index.normalize().unique()
    return df[df.index.normalize() == dates[-1]]


def intraday_signals(symbol: str, intra: pd.DataFrame, daily: pd.DataFrame,
                     reward_risk: float = 2.0) -> list[IntradaySignal]:
    """Generate intraday signals from 5-minute bars for the latest session."""
    signals: list[IntradaySignal] = []
    session = _last_session(intra)
    if len(session) < 6:
        return signals

    last = float(session["Close"].iloc[-1])
    day_atr = float(ta.atr(daily).iloc[-1])
    trend_daily = float(ta.supertrend(daily).iloc[-1])
    adx_daily = float(ta.adx(daily).iloc[-1])

    # True intraday VWAP for the session.
    session = session.copy()
    session["VWAP"] = ta.vwap(session)
    vwap_now = float(session["VWAP"].iloc[-1])
    avg_vol = float(session["Volume"].mean()) or 1.0
    recent_vol = float(session["Volume"].tail(3).mean())

    # ---- 1. Opening Range Breakout (first 30 min = 6 x 5m bars)
    orb = session.iloc[:6]
    orb_high, orb_low = float(orb["High"].max()), float(orb["Low"].min())
    if last > orb_high and trend_daily > 0 and recent_vol > 1.2 * avg_vol:
        risk = max(last - orb_low, 0.3 * day_atr)
        signals.append(IntradaySignal(
            symbol, "ORB breakout", "BUY", last, round(last - risk, 2),
            round(last + reward_risk * risk, 2),
            f"Broke above 30-min opening range high {orb_high:.2f} on "
            f"{recent_vol/avg_vol:.1f}x volume with daily uptrend",
            confidence=min(0.9, 0.5 + 0.2 * (adx_daily > 25) + 0.2 * (last > vwap_now)),
        ))
    elif last < orb_low and trend_daily < 0 and recent_vol > 1.2 * avg_vol:
        risk = max(orb_high - last, 0.3 * day_atr)
        signals.append(IntradaySignal(
            symbol, "ORB breakdown", "SELL", last, round(last + risk, 2),
            round(last - reward_risk * risk, 2),
            f"Broke below 30-min opening range low {orb_low:.2f} on volume "
            f"with daily downtrend",
            confidence=min(0.9, 0.5 + 0.2 * (adx_daily > 25) + 0.2 * (last < vwap_now)),
        ))

    # ---- 2. VWAP strategies
    dev = (last - vwap_now) / vwap_now
    if abs(dev) > 0.015 and adx_daily < 25:
        # Stretched >1.5% from VWAP in a non-trending market -> mean reversion
        side = "SELL" if dev > 0 else "BUY"
        risk = 0.5 * day_atr
        tgt = vwap_now
        signals.append(IntradaySignal(
            symbol, "VWAP mean reversion", side, last,
            round(last + risk, 2) if side == "SELL" else round(last - risk, 2),
            round(tgt, 2),
            f"Price {dev*100:+.1f}% from VWAP ({vwap_now:.2f}) in a range-bound "
            f"market (ADX {adx_daily:.0f}) — institutions fade the stretch",
            confidence=0.55,
        ))
    elif 0 < dev < 0.01 and trend_daily > 0 and adx_daily >= 25:
        # Holding just above VWAP in a strong uptrend -> trend continuation
        risk = max(last - vwap_now, 0.4 * day_atr)
        signals.append(IntradaySignal(
            symbol, "VWAP trend continuation", "BUY", last,
            round(vwap_now - 0.2 * day_atr, 2), round(last + reward_risk * risk, 2),
            f"Holding above rising VWAP ({vwap_now:.2f}) with trend strength "
            f"ADX {adx_daily:.0f} — buy pullbacks toward VWAP",
            confidence=0.65,
        ))

    # ---- 3. Momentum with Supertrend confirmation
    day_open = float(session["Open"].iloc[0])
    day_move = (last - day_open) / day_open
    if day_move > 0.02 and trend_daily > 0 and last > vwap_now:
        risk = 0.8 * day_atr
        signals.append(IntradaySignal(
            symbol, "Momentum (trend-confirmed)", "BUY", last,
            round(last - risk, 2), round(last + reward_risk * risk, 2),
            f"Up {day_move*100:.1f}% intraday, above VWAP, daily Supertrend "
            f"bullish — momentum desks ride strength",
            confidence=min(0.85, 0.5 + day_move * 5),
        ))
    elif day_move < -0.02 and trend_daily < 0 and last < vwap_now:
        risk = 0.8 * day_atr
        signals.append(IntradaySignal(
            symbol, "Momentum (trend-confirmed)", "SELL", last,
            round(last + risk, 2), round(last - reward_risk * risk, 2),
            f"Down {day_move*100:.1f}% intraday, below VWAP, daily Supertrend "
            f"bearish — short the weakness",
            confidence=min(0.85, 0.5 + abs(day_move) * 5),
        ))

    return signals
