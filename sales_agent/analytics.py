"""Deterministic analytics primitives — every number the app or the AI layer
shows to the user is computed here with plain pandas, never guessed by a model."""
from __future__ import annotations

import pandas as pd

FREQ_MAP = {"day": "D", "week": "W", "month": "ME", "quarter": "QE", "year": "YE"}


def kpis(df: pd.DataFrame, amount_col: str | None, date_col: str | None) -> dict:
    out = {"row_count": len(df)}
    if amount_col:
        out["total"] = float(df[amount_col].sum())
        out["average"] = float(df[amount_col].mean())
        out["median"] = float(df[amount_col].median())
        out["max"] = float(df[amount_col].max())
        out["min"] = float(df[amount_col].min())
    if date_col:
        valid = df[date_col].dropna()
        if len(valid):
            out["date_start"] = valid.min()
            out["date_end"] = valid.max()
    return out


def trend(df: pd.DataFrame, date_col: str, amount_col: str, freq: str = "M", agg: str = "sum") -> pd.Series:
    freq = FREQ_MAP.get(freq, freq)
    s = df.dropna(subset=[date_col]).set_index(date_col)[amount_col]
    grouped = s.resample(freq).agg(agg)
    return grouped


def breakdown(df: pd.DataFrame, dim_col: str, metric_col: str, agg: str = "sum") -> pd.Series:
    s = df.groupby(dim_col)[metric_col].agg(agg).sort_values(ascending=False)
    return s


def top_n(df: pd.DataFrame, dim_col: str, metric_col: str, n: int = 10, agg: str = "sum", ascending: bool = False) -> pd.Series:
    s = df.groupby(dim_col)[metric_col].agg(agg).sort_values(ascending=ascending)
    return s.head(n)


def growth_rate(df: pd.DataFrame, date_col: str, amount_col: str, freq: str = "M") -> pd.Series:
    s = trend(df, date_col, amount_col, freq=freq)
    return s.pct_change() * 100


def filter_rows(df: pd.DataFrame, column: str, op: str, value) -> pd.DataFrame:
    if op == "eq":
        return df[df[column] == value]
    if op == "contains":
        return df[df[column].astype(str).str.contains(str(value), case=False, na=False)]
    if op == "gt":
        return df[df[column] > value]
    if op == "lt":
        return df[df[column] < value]
    if op == "gte":
        return df[df[column] >= value]
    if op == "lte":
        return df[df[column] <= value]
    return df
