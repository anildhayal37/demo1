"""Sales Analytics AI — Streamlit app.

Upload CSV(s), get instant KPIs and charts, then ask questions in plain
English. Rule-based analytics work with no setup; set ANTHROPIC_API_KEY
to let Claude interpret more open-ended questions.

Run with: streamlit run sales_agent/app.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

if __package__ in (None, ""):
    # `streamlit run sales_agent/app.py` executes this file as a top-level
    # script, so relative imports fail — put the repo root on sys.path and
    # import the package by name instead.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sales_agent import ai_query, analytics, query_engine
    from sales_agent.data_utils import ColumnProfile, detect_columns, load_csvs
else:
    from . import ai_query, analytics, query_engine
    from .data_utils import ColumnProfile, detect_columns, load_csvs

st.set_page_config(page_title="Sales Analytics AI", page_icon="📊", layout="wide")


def _render_table_and_chart(table, chart_type: str | None) -> None:
    if table is None:
        return
    if isinstance(table, pd.Series):
        display_df = table.rename("value").to_frame()
    else:
        display_df = table
    st.dataframe(display_df, width="stretch")
    if chart_type == "bar" and isinstance(table, pd.Series):
        st.bar_chart(table)
    elif chart_type == "line" and isinstance(table, pd.Series):
        st.line_chart(table)


def _render_kpis(df: pd.DataFrame, cols: ColumnProfile) -> None:
    k = analytics.kpis(df, cols.amount_col, cols.date_col)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{k['row_count']:,}")
    if "total" in k:
        c2.metric(f"Total {cols.amount_col}", f"{k['total']:,.0f}")
        c3.metric(f"Average {cols.amount_col}", f"{k['average']:,.2f}")
        c4.metric(f"Max {cols.amount_col}", f"{k['max']:,.0f}")
    if "date_start" in k:
        st.caption(f"Date range: {k['date_start'].date()} → {k['date_end'].date()}")


def _render_overview_charts(df: pd.DataFrame, cols: ColumnProfile) -> None:
    left, right = st.columns(2)
    if cols.date_col and cols.amount_col:
        with left:
            st.subheader("Trend over time")
            freq = st.selectbox("Frequency", ["day", "week", "month", "quarter", "year"], index=2, key="trend_freq")
            series = analytics.trend(df, cols.date_col, cols.amount_col, freq=freq)
            st.line_chart(series)
    if cols.categorical_cols and cols.amount_col:
        with right:
            st.subheader("Top breakdown")
            dim = st.selectbox("Category", cols.categorical_cols, key="breakdown_dim")
            series = analytics.top_n(df, dim, cols.amount_col, n=10)
            st.bar_chart(series)


def main() -> None:
    st.title("📊 Sales Analytics AI")
    st.caption("Upload sales CSV(s), get instant analytics, then ask questions in plain English.")

    with st.sidebar:
        st.header("Data")
        uploaded = st.file_uploader("Upload sales CSV file(s)", type=["csv"], accept_multiple_files=True)
        use_sample = st.button("Use sample data")

        st.header("Assistant")
        ai_ready = ai_query.is_available()
        use_ai = st.toggle(
            "Use Claude for open-ended questions",
            value=ai_ready,
            disabled=not ai_ready,
            help="Requires `pip install anthropic` and ANTHROPIC_API_KEY (or `ant auth login`). "
                 "Falls back to a rule-based engine otherwise.",
        )
        if not ai_ready:
            st.caption("Rule-based mode only — `pip install anthropic` to enable Claude.")

    if use_sample:
        st.session_state["df"], _ = load_csvs([open(_sample_path(), "rb")])
        st.session_state.pop("chat", None)
    elif uploaded:
        df, warnings = load_csvs(uploaded)
        for w in warnings:
            st.sidebar.warning(w)
        if df is not None:
            st.session_state["df"] = df
            st.session_state.pop("chat", None)

    df = st.session_state.get("df")
    if df is None:
        st.info("Upload one or more CSV files, or click **Use sample data** in the sidebar to try it out.")
        return

    cols = detect_columns(df)

    with st.sidebar:
        st.header("Detected columns")
        cols.date_col = st.selectbox(
            "Date column", [None] + list(df.columns),
            index=(list(df.columns).index(cols.date_col) + 1) if cols.date_col else 0,
        )
        cols.amount_col = st.selectbox(
            "Amount / revenue column", [None] + cols.numeric_cols,
            index=(cols.numeric_cols.index(cols.amount_col) + 1) if cols.amount_col in cols.numeric_cols else 0,
        )
        if cols.date_col:
            df[cols.date_col] = pd.to_datetime(df[cols.date_col], errors="coerce")

    st.subheader("Preview")
    st.dataframe(df.head(20), width="stretch")

    st.subheader("Key metrics")
    _render_kpis(df, cols)
    _render_overview_charts(df, cols)

    st.subheader("Ask a question")
    st.caption("e.g. \"top 5 products by sales\", \"sales trend by month\", \"average order value by region\"")

    if "chat" not in st.session_state:
        st.session_state["chat"] = []

    for entry in st.session_state["chat"]:
        with st.chat_message(entry["role"]):
            st.write(entry["text"])
            if entry.get("table") is not None:
                _render_table_and_chart(entry["table"], entry.get("chart_type"))

    prompt = st.chat_input("Ask about your sales data...")
    if prompt:
        st.session_state["chat"].append({"role": "user", "text": prompt})
        with st.spinner("Analyzing..."):
            result = None
            if use_ai and ai_ready:
                result = ai_query.answer(df, cols, prompt)
            if result is None:
                result = query_engine.answer(df, cols, prompt)
        st.session_state["chat"].append({
            "role": "assistant",
            "text": result.text,
            "table": result.table,
            "chart_type": result.chart_type,
        })
        st.rerun()


def _sample_path() -> str:
    return os.path.join(os.path.dirname(__file__), "sample_data", "sales_sample.csv")


if __name__ == "__main__":
    main()
