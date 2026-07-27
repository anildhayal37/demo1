"""Optional Claude-powered natural-language layer.

Two calls, both small and cheap:
  1. Turn the user's question into a small structured spec (dimension, metric,
     aggregation, ...), validated against the columns that actually exist in
     the uploaded data.
  2. Compute the exact answer deterministically with pandas (`analytics.py`),
     then ask Claude to turn the *computed numbers* into a short narrative.

Claude never touches the raw dataframe and never generates code that runs
against it — this keeps the feature safe (no `exec`/`eval` of model output)
and accurate (numbers always come from pandas, not from the model).

Requires `pip install anthropic` and credentials (ANTHROPIC_API_KEY or an
`ant auth login` profile). Degrades gracefully when unavailable — callers
should fall back to `query_engine.answer()`.
"""
from __future__ import annotations

import json

import pandas as pd

from . import analytics
from .data_utils import ColumnProfile
from .query_engine import AnswerResult

MODEL = "claude-opus-5"

VALID_OPERATIONS = {"kpi", "top_n", "breakdown", "trend", "growth"}
VALID_AGGS = {"sum", "mean", "count", "max", "min", "median"}
VALID_FREQS = {"day", "week", "month", "quarter", "year"}

SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": sorted(VALID_OPERATIONS)},
        "dimension": {"type": ["string", "null"]},
        "metric": {"type": ["string", "null"]},
        "agg": {"type": ["string", "null"], "enum": sorted(VALID_AGGS) + [None]},
        "n": {"type": ["integer", "null"]},
        "freq": {"type": ["string", "null"], "enum": sorted(VALID_FREQS) + [None]},
        "ascending": {"type": ["boolean", "null"]},
    },
    "required": ["operation", "dimension", "metric", "agg", "n", "freq", "ascending"],
    "additionalProperties": False,
}


def is_available() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _schema_summary(df: pd.DataFrame, cols: ColumnProfile) -> str:
    lines = [f"Rows: {len(df)}"]
    if cols.date_col:
        lines.append(f"Date column: {cols.date_col}")
    lines.append(f"Numeric columns (metrics): {cols.numeric_cols}")
    lines.append(f"Category columns (dimensions): {cols.categorical_cols}")
    for c in cols.categorical_cols[:6]:
        sample = df[c].dropna().unique()[:8].tolist()
        lines.append(f"  '{c}' sample values: {sample}")
    return "\n".join(lines)


def _parse_spec(client, prompt: str, df: pd.DataFrame, cols: ColumnProfile) -> dict:
    system = (
        "You convert a sales-analytics question into a structured query spec. "
        "Only use column names exactly as given in the schema. "
        "operation meanings: kpi=overall summary, top_n=ranked list by a dimension, "
        "breakdown=full grouped total by a dimension (no ranking), "
        "trend=metric over time by frequency, growth=% change over time. "
        "Use null for any field that doesn't apply."
    )
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        output_config={"format": {"type": "json_schema", "schema": SPEC_SCHEMA}},
        messages=[{
            "role": "user",
            "content": f"Data schema:\n{_schema_summary(df, cols)}\n\nQuestion: {prompt}",
        }],
    )
    text = next(b.text for b in message.content if b.type == "text")
    return json.loads(text)


def _validate_spec(spec: dict, cols: ColumnProfile) -> dict:
    valid_metrics = set(cols.all_metrics)
    valid_dims = set(cols.categorical_cols)
    return {
        "operation": spec.get("operation") if spec.get("operation") in VALID_OPERATIONS else "kpi",
        "dimension": spec.get("dimension") if spec.get("dimension") in valid_dims else (cols.categorical_cols[0] if cols.categorical_cols else None),
        "metric": spec.get("metric") if spec.get("metric") in valid_metrics else cols.amount_col,
        "agg": spec.get("agg") if spec.get("agg") in VALID_AGGS else "sum",
        "n": max(1, min(int(spec["n"]), 100)) if spec.get("n") else 10,
        "freq": spec.get("freq") if spec.get("freq") in VALID_FREQS else "month",
        "ascending": bool(spec.get("ascending")),
    }


def _execute_spec(df: pd.DataFrame, cols: ColumnProfile, spec: dict) -> tuple[str, object, str | None]:
    op = spec["operation"]
    metric = spec["metric"]
    if op == "top_n" and spec["dimension"] and metric:
        table = analytics.top_n(df, spec["dimension"], metric, n=spec["n"], agg=spec["agg"], ascending=spec["ascending"])
        return f"{spec['agg']} of {metric} by {spec['dimension']}", table, "bar"
    if op == "breakdown" and spec["dimension"] and metric:
        table = analytics.breakdown(df, spec["dimension"], metric, agg=spec["agg"])
        return f"{spec['agg']} of {metric} by {spec['dimension']}", table, "bar"
    if op == "trend" and cols.date_col and metric:
        table = analytics.trend(df, cols.date_col, metric, freq=spec["freq"], agg=spec["agg"])
        return f"{spec['agg']} of {metric} by {spec['freq']}", table, "line"
    if op == "growth" and cols.date_col and metric:
        table = analytics.growth_rate(df, cols.date_col, metric, freq=spec["freq"])
        return f"% change in {metric} by {spec['freq']}", table, "line"
    k = analytics.kpis(df, cols.amount_col, cols.date_col)
    return "overall summary", pd.Series(k), None


def _narrate(client, prompt: str, description: str, table: object) -> str:
    if isinstance(table, (pd.Series, pd.DataFrame)):
        payload = table.head(30).to_string()
    else:
        payload = str(table)
    message = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=(
            "You are a sales analyst. You are given the exact computed result for a "
            "user's question. Write a short, direct answer (2-5 sentences) referencing "
            "the real numbers shown. Do not invent numbers not present in the data."
        ),
        messages=[{
            "role": "user",
            "content": f"Question: {prompt}\n\nComputed result ({description}):\n{payload}\n\nWrite the answer.",
        }],
    )
    return "".join(b.text for b in message.content if b.type == "text")


def answer(df: pd.DataFrame, cols: ColumnProfile, prompt: str) -> AnswerResult | None:
    """Return an AI-narrated AnswerResult, or None if the AI layer is unavailable."""
    try:
        import anthropic
    except ImportError:
        return None

    try:
        client = anthropic.Anthropic()
        raw_spec = _parse_spec(client, prompt, df, cols)
        spec = _validate_spec(raw_spec, cols)
        description, table, chart_type = _execute_spec(df, cols, spec)
        narrative = _narrate(client, prompt, description, table)
        return AnswerResult(narrative, table, chart_type)
    except Exception:
        return None
