"""Technical indicators used by professional trading desks.

All functions take a pandas DataFrame with columns Open/High/Low/Close/Volume
(daily or intraday bars) and return pandas Series aligned to the input index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid + num_std * std, mid, mid - num_std * std


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price — the institutional benchmark.

    For daily data this is a rolling proxy; for true intraday VWAP feed
    intraday bars grouped by session.
    """
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_pv = (typical * df["Volume"]).cumsum()
    cum_v = df["Volume"].cumsum().replace(0, np.nan)
    return cum_pv / cum_v


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    """Returns +1 (uptrend) / -1 (downtrend) per bar."""
    _atr = atr(df, period)
    hl2 = (df["High"] + df["Low"]) / 2
    upper = hl2 + multiplier * _atr
    lower = hl2 - multiplier * _atr
    close = df["Close"]

    trend = pd.Series(index=df.index, dtype=float)
    ub, lb = upper.copy(), lower.copy()
    for i in range(1, len(df)):
        ub.iloc[i] = min(upper.iloc[i], ub.iloc[i - 1]) if close.iloc[i - 1] <= ub.iloc[i - 1] else upper.iloc[i]
        lb.iloc[i] = max(lower.iloc[i], lb.iloc[i - 1]) if close.iloc[i - 1] >= lb.iloc[i - 1] else lower.iloc[i]
        if close.iloc[i] > ub.iloc[i - 1]:
            trend.iloc[i] = 1
        elif close.iloc[i] < lb.iloc[i - 1]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i - 1] if not np.isnan(trend.iloc[i - 1]) else 1
    return trend.fillna(1)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — trend strength (>25 = trending)."""
    high, low = df["High"], df["Low"]
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    _atr = atr(df, period).replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / _atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / _atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()
