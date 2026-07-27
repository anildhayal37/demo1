"""CSV loading and column-role detection for the sales analytics agent."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

AMOUNT_KEYWORDS = ["revenue", "sales", "amount", "total", "price", "value", "net", "gross", "profit"]
QUANTITY_KEYWORDS = ["qty", "quantity", "units", "count"]
DATE_KEYWORDS = ["date", "time", "month", "year", "period", "day"]
ID_KEYWORDS = ["id", "code", "zip", "postal", "phone"]


@dataclass
class ColumnProfile:
    date_col: str | None
    amount_col: str | None
    quantity_col: str | None
    numeric_cols: list[str] = field(default_factory=list)
    categorical_cols: list[str] = field(default_factory=list)

    @property
    def all_dims(self) -> list[str]:
        return list(self.categorical_cols)

    @property
    def all_metrics(self) -> list[str]:
        cols = list(self.numeric_cols)
        if self.amount_col and self.amount_col not in cols:
            cols.insert(0, self.amount_col)
        return cols


def load_csvs(files) -> tuple[pd.DataFrame | None, list[str]]:
    """Load one or more uploaded CSV files into a single DataFrame.

    Multiple files are concatenated only if they share the same columns;
    otherwise only the first file is used and a warning is returned.
    """
    warnings: list[str] = []
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception as e:
            warnings.append(f"Could not read '{f.name}': {e}")
            continue
        df.columns = [str(c).strip() for c in df.columns]
        frames.append((f.name, df))

    if not frames:
        return None, warnings

    base_cols = set(frames[0][1].columns)
    combined = [frames[0][1]]
    for name, df in frames[1:]:
        if set(df.columns) == base_cols:
            combined.append(df)
        else:
            warnings.append(f"Skipped '{name}': columns don't match the first file.")

    result = pd.concat(combined, ignore_index=True) if len(combined) > 1 else combined[0]
    return result, warnings


def _score_amount_column(name: str) -> int:
    lname = name.lower()
    return sum(kw in lname for kw in AMOUNT_KEYWORDS)


def detect_columns(df: pd.DataFrame) -> ColumnProfile:
    date_col = None
    best_ratio = 0.0
    for col in df.columns:
        if df[col].dtype == "object" or "date" in col.lower() or "time" in col.lower():
            parsed = pd.to_datetime(df[col], errors="coerce", format="mixed")
            ratio = parsed.notna().mean() if len(df) else 0
            name_bonus = 0.15 if any(k in col.lower() for k in DATE_KEYWORDS) else 0
            score = ratio + name_bonus
            if ratio > 0.7 and score > best_ratio:
                best_ratio = score
                date_col = col
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce", format="mixed")

    numeric_cols = [
        c for c in df.select_dtypes(include="number").columns
        if not any(k in c.lower() for k in ID_KEYWORDS)
    ]

    amount_col = None
    if numeric_cols:
        best_score = max(_score_amount_column(c) for c in numeric_cols)
        if best_score > 0:
            top_scored = [c for c in numeric_cols if _score_amount_column(c) == best_score]
            amount_col = max(top_scored, key=lambda c: df[c].sum())
        else:
            non_qty = [c for c in numeric_cols if not any(k in c.lower() for k in QUANTITY_KEYWORDS)]
            candidates = non_qty or numeric_cols
            amount_col = max(candidates, key=lambda c: df[c].sum())

    quantity_col = next(
        (c for c in numeric_cols if any(k in c.lower() for k in QUANTITY_KEYWORDS)), None
    )

    n = len(df)
    categorical_cols = []
    for col in df.columns:
        if col == date_col or col in numeric_cols:
            continue
        nunique = df[col].nunique(dropna=True)
        if 1 < nunique <= max(50, int(n * 0.5)):
            categorical_cols.append(col)

    return ColumnProfile(
        date_col=date_col,
        amount_col=amount_col,
        quantity_col=quantity_col,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
    )
