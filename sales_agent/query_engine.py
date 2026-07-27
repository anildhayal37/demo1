"""Rule-based natural-language query engine.

Parses a handful of common analytics phrasings ("top 5 products by revenue",
"sales trend by month", "average order value by region") into calls against
`analytics.py`. Works with no API key so the app is useful out of the box;
`ai_query.py` layers a Claude-powered version of the same idea on top.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from . import analytics
from .data_utils import ColumnProfile

AGG_WORDS = {
    "average": "mean", "avg": "mean", "mean": "mean",
    "total": "sum", "sum": "sum",
    "count": "count", "how many": "count",
    "max": "max", "maximum": "max", "highest": "max",
    "min": "min", "minimum": "min", "lowest": "min",
}
FREQ_WORDS = {
    "daily": "day", "day": "day", "per day": "day",
    "weekly": "week", "week": "week",
    "monthly": "month", "month": "month",
    "quarterly": "quarter", "quarter": "quarter",
    "yearly": "year", "annual": "year", "year": "year",
}


@dataclass
class AnswerResult:
    text: str
    table: pd.DataFrame | pd.Series | None = None
    chart_type: str | None = None  # "bar" | "line" | None


def _find_metric(prompt: str, cols: ColumnProfile) -> str | None:
    lp = prompt.lower()
    for c in cols.numeric_cols:
        if c.lower() in lp:
            return c
    return cols.amount_col


def _find_dimension(prompt: str, cols: ColumnProfile) -> str | None:
    lp = prompt.lower()
    for c in cols.categorical_cols:
        if c.lower() in lp or c.lower().rstrip("s") in lp:
            return c
    m = re.search(r"\bby\s+([a-zA-Z_ ]+)", lp)
    if m:
        fragment = m.group(1).strip()
        for c in cols.categorical_cols:
            if c.lower() in fragment or fragment in c.lower():
                return c
    return cols.categorical_cols[0] if cols.categorical_cols else None


def _find_agg(prompt: str) -> str:
    lp = prompt.lower()
    for word, agg in AGG_WORDS.items():
        if word in lp:
            return agg
    return "sum"


def _find_freq(prompt: str) -> str:
    lp = prompt.lower()
    for word, freq in FREQ_WORDS.items():
        if word in lp:
            return freq
    return "month"


def answer(df: pd.DataFrame, cols: ColumnProfile, prompt: str) -> AnswerResult:
    lp = prompt.lower().strip()

    n_match = re.search(r"\b(top|bottom|best|worst)\s+(\d+)", lp)
    if n_match:
        direction, n = n_match.group(1), int(n_match.group(2))
        ascending = direction in ("bottom", "worst")
        dim = _find_dimension(lp, cols)
        metric = _find_metric(lp, cols)
        agg = _find_agg(lp)
        if not dim or not metric:
            return AnswerResult("I couldn't find a category or metric to rank — try naming a column, e.g. 'top 5 products by sales'.")
        table = analytics.top_n(df, dim, metric, n=n, agg=agg, ascending=ascending)
        label = "bottom" if ascending else "top"
        text = f"{label.capitalize()} {n} {dim} by {agg} of {metric}:"
        return AnswerResult(text, table, chart_type="bar")

    if "growth" in lp or "% change" in lp or "percent change" in lp:
        if not cols.date_col:
            return AnswerResult("No date column was detected, so I can't compute growth rate.")
        metric = _find_metric(lp, cols)
        freq = _find_freq(lp)
        table = analytics.growth_rate(df, cols.date_col, metric, freq=freq)
        text = f"% change in {metric} period-over-period ({freq}):"
        return AnswerResult(text, table, chart_type="line")

    if any(w in lp for w in ["trend", "over time", "by month", "by week", "by day", "by year", "by quarter", "monthly", "weekly", "daily", "yearly"]):
        if not cols.date_col:
            return AnswerResult("No date column was detected in this data, so I can't chart a trend.")
        metric = _find_metric(lp, cols)
        agg = _find_agg(lp)
        freq = _find_freq(lp)
        table = analytics.trend(df, cols.date_col, metric, freq=freq, agg=agg)
        text = f"{agg.capitalize()} of {metric} by {freq}:"
        return AnswerResult(text, table, chart_type="line")

    if any(w in lp for w in ["summary", "overview", "describe", "stats", "kpi", "how much", "how many"]):
        k = analytics.kpis(df, cols.amount_col, cols.date_col)
        lines = [f"Rows: {k['row_count']:,}"]
        if "total" in k:
            lines.append(f"Total {cols.amount_col}: {k['total']:,.2f}")
            lines.append(f"Average {cols.amount_col}: {k['average']:,.2f}")
            lines.append(f"Min / Max {cols.amount_col}: {k['min']:,.2f} / {k['max']:,.2f}")
        if "date_start" in k:
            lines.append(f"Date range: {k['date_start'].date()} to {k['date_end'].date()}")
        return AnswerResult("\n".join(lines))

    dim = _find_dimension(lp, cols)
    metric = _find_metric(lp, cols)
    agg = _find_agg(lp)
    if dim and metric and (" by " in lp or dim.lower() in lp):
        table = analytics.breakdown(df, dim, metric, agg=agg)
        text = f"{agg.capitalize()} of {metric} by {dim}:"
        return AnswerResult(text, table, chart_type="bar")

    k = analytics.kpis(df, cols.amount_col, cols.date_col)
    lines = ["I wasn't able to match a specific analysis, so here's a quick summary:", f"Rows: {k['row_count']:,}"]
    if "total" in k:
        lines.append(f"Total {cols.amount_col}: {k['total']:,.2f}")
    lines.append("Try asking things like: 'top 5 products by sales', 'sales trend by month', 'average order value by region'.")
    return AnswerResult("\n".join(lines))
