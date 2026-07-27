# Sales Analytics AI

A Streamlit agent that turns uploaded sales CSVs into instant analytics:
upload a file, get auto-detected KPIs and charts, then ask questions in
plain English ("top 5 products by sales", "revenue trend by month",
"average order value by region").

## How it works

1. **Column detection** (`data_utils.py`) — auto-detects the date column,
   the revenue/amount column, and categorical dimensions (product, region,
   channel, ...) from the uploaded CSV(s).
2. **Deterministic analytics** (`analytics.py`) — KPIs, trends, breakdowns,
   top-N rankings, and growth rate, all plain pandas. Every number shown in
   the UI comes from here — nothing is guessed by a model.
3. **Rule-based query engine** (`query_engine.py`) — parses common phrasings
   ("top N ... by ...", "trend by month", "average X by Y") into calls
   against `analytics.py`. Works with zero setup.
4. **Optional AI layer** (`ai_query.py`) — if `anthropic` is installed and
   credentials are configured, Claude converts open-ended questions into a
   small validated query spec (whitelisted columns/operations only — no
   generated code ever runs against the data), then writes a short
   narrative over the *computed* result. Falls back to the rule-based
   engine automatically if unavailable.

## Install

```bash
pip install -r sales_agent/requirements.txt

# Optional, for Claude-powered open-ended questions:
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...   # or `ant auth login`
```

## Run

```bash
streamlit run sales_agent/app.py
```

Upload your own sales CSV, or click **Use sample data** in the sidebar to
try it immediately with a bundled 18-month synthetic dataset
(`sample_data/sales_sample.csv`).

## Example questions

- "top 5 products by sales"
- "sales trend by month"
- "average order value by region"
- "total sales by channel"
- "growth rate by quarter"
- "bottom 3 sales reps by revenue"
