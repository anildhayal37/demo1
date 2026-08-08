"""
Technical indicators + a composite BUY / SELL / HOLD signal.

Everything here is pure-Python (no numpy) so the whole app runs on a stock
Python install with zero third-party packages. Functions operate on plain
lists of closing prices, oldest first.
"""
from __future__ import annotations

from typing import List, Optional


# ── basic moving averages ────────────────────────────────────────────────────

def sma(values: List[float], period: int) -> List[Optional[float]]:
    """Simple moving average. Returns a list aligned with `values`;
    entries before enough data are None."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return out
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """Exponential moving average, aligned with `values`."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or not values:
        return out
    k = 2.0 / (period + 1)
    # seed with the SMA of the first `period` values for stability
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


# ── oscillators ──────────────────────────────────────────────────────────────

def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """Relative Strength Index (Wilder's smoothing)."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram), each aligned with values."""
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # signal line = EMA of the macd line (only over the defined part)
    defined = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    signal_line: List[Optional[float]] = [None] * len(values)
    if len(defined) >= signal:
        seq = [v for _, v in defined]
        sig = ema(seq, signal)
        for (orig_i, _), s in zip(defined, sig):
            signal_line[orig_i] = s

    hist: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if macd_line[i] is not None and signal_line[i] is not None:
            hist[i] = macd_line[i] - signal_line[i]
    return macd_line, signal_line, hist


def bollinger(values: List[float], period: int = 20, mult: float = 2.0):
    """Returns (upper, mid, lower) Bollinger bands aligned with values."""
    mid = sma(values, period)
    upper: List[Optional[float]] = [None] * len(values)
    lower: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i >= period - 1:
            window = values[i - period + 1: i + 1]
            m = mid[i]
            var = sum((x - m) ** 2 for x in window) / period
            sd = var ** 0.5
            upper[i] = m + mult * sd
            lower[i] = m - mult * sd
    return upper, lower, mid  # note: returns upper, lower, mid


# ── composite signal ─────────────────────────────────────────────────────────

def compute_signal(closes: List[float]) -> dict:
    """
    Combine several indicators into one advisory signal.

    Returns a dict:
      {
        "action": "BUY" | "SELL" | "HOLD",
        "score": float in [-1, 1]   (negative = bearish, positive = bullish),
        "confidence": int 0..100,
        "reasons": [ {"text": str, "bias": "bullish"|"bearish"|"neutral"}, ... ],
        "indicators": { latest values for display }
      }
    """
    n = len(closes)
    if n < 35:
        return {
            "action": "HOLD",
            "score": 0.0,
            "confidence": 0,
            "reasons": [{"text": "Not enough data yet to read the market.",
                         "bias": "neutral"}],
            "indicators": {},
        }

    rsi_vals = rsi(closes, 14)
    macd_line, signal_line, hist = macd(closes)
    upper, lower, mid = bollinger(closes, 20, 2.0)
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50) if n >= 50 else [None] * n

    price = closes[-1]
    rsi_now = rsi_vals[-1]
    hist_now = hist[-1]
    hist_prev = hist[-2] if n >= 2 else None
    macd_now = macd_line[-1]
    sig_now = signal_line[-1]
    up_now = upper[-1]
    lo_now = lower[-1]
    sma20_now = sma20[-1]
    sma50_now = sma50[-1]

    # weighted votes; each contributes to a [-1, 1] score
    votes = []          # (weight, direction in [-1,1])
    reasons = []

    # RSI ---------------------------------------------------------------
    if rsi_now is not None:
        if rsi_now < 30:
            votes.append((0.30, 1.0))
            reasons.append({"text": f"RSI {rsi_now:.0f} — oversold, bounce likely.",
                            "bias": "bullish"})
        elif rsi_now > 70:
            votes.append((0.30, -1.0))
            reasons.append({"text": f"RSI {rsi_now:.0f} — overbought, pullback likely.",
                            "bias": "bearish"})
        elif rsi_now < 45:
            votes.append((0.12, 0.5))
            reasons.append({"text": f"RSI {rsi_now:.0f} — leaning weak/cheap.",
                            "bias": "bullish"})
        elif rsi_now > 55:
            votes.append((0.12, -0.5))
            reasons.append({"text": f"RSI {rsi_now:.0f} — leaning strong/expensive.",
                            "bias": "bearish"})
        else:
            reasons.append({"text": f"RSI {rsi_now:.0f} — neutral.", "bias": "neutral"})

    # MACD --------------------------------------------------------------
    if hist_now is not None and hist_prev is not None:
        crossed_up = hist_prev <= 0 < hist_now
        crossed_down = hist_prev >= 0 > hist_now
        if crossed_up:
            votes.append((0.30, 1.0))
            reasons.append({"text": "MACD just crossed above its signal line — momentum turning up.",
                            "bias": "bullish"})
        elif crossed_down:
            votes.append((0.30, -1.0))
            reasons.append({"text": "MACD just crossed below its signal line — momentum turning down.",
                            "bias": "bearish"})
        elif hist_now > 0:
            votes.append((0.15, 0.6))
            reasons.append({"text": "MACD above signal — bullish momentum.",
                            "bias": "bullish"})
        elif hist_now < 0:
            votes.append((0.15, -0.6))
            reasons.append({"text": "MACD below signal — bearish momentum.",
                            "bias": "bearish"})

    # Bollinger ---------------------------------------------------------
    if up_now is not None and lo_now is not None:
        if price <= lo_now:
            votes.append((0.20, 1.0))
            reasons.append({"text": "Price at/under the lower Bollinger band — stretched cheap.",
                            "bias": "bullish"})
        elif price >= up_now:
            votes.append((0.20, -1.0))
            reasons.append({"text": "Price at/over the upper Bollinger band — stretched rich.",
                            "bias": "bearish"})

    # Trend (SMA stack) -------------------------------------------------
    if sma20_now is not None and sma50_now is not None:
        if sma20_now > sma50_now:
            votes.append((0.20, 0.7))
            reasons.append({"text": "20-period average above 50-period — uptrend.",
                            "bias": "bullish"})
        else:
            votes.append((0.20, -0.7))
            reasons.append({"text": "20-period average below 50-period — downtrend.",
                            "bias": "bearish"})
    elif sma20_now is not None:
        if price > sma20_now:
            votes.append((0.10, 0.5))
            reasons.append({"text": "Price above its 20-period average.",
                            "bias": "bullish"})
        else:
            votes.append((0.10, -0.5))
            reasons.append({"text": "Price below its 20-period average.",
                            "bias": "bearish"})

    total_w = sum(w for w, _ in votes)
    score = sum(w * d for w, d in votes) / total_w if total_w else 0.0
    score = max(-1.0, min(1.0, score))

    if score >= 0.33:
        action = "BUY"
    elif score <= -0.33:
        action = "SELL"
    else:
        action = "HOLD"

    confidence = int(round(abs(score) * 100))

    return {
        "action": action,
        "score": round(score, 3),
        "confidence": confidence,
        "reasons": reasons,
        "indicators": {
            "price": price,
            "rsi": round(rsi_now, 1) if rsi_now is not None else None,
            "macd": round(macd_now, 4) if macd_now is not None else None,
            "macd_signal": round(sig_now, 4) if sig_now is not None else None,
            "macd_hist": round(hist_now, 4) if hist_now is not None else None,
            "bb_upper": round(up_now, 2) if up_now is not None else None,
            "bb_lower": round(lo_now, 2) if lo_now is not None else None,
            "sma20": round(sma20_now, 2) if sma20_now is not None else None,
            "sma50": round(sma50_now, 2) if sma50_now is not None else None,
        },
        "series": {
            "sma20": sma20,
            "sma50": sma50,
            "bb_upper": upper,
            "bb_lower": lower,
            "rsi": rsi_vals,
        },
    }
