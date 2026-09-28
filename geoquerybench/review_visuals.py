"""Pure helpers for GeoQueryBench result exploration and commodity filters."""

from __future__ import annotations

from io import BytesIO
import json
import re

import pandas as pd


COMMODITY_ALIASES = {
    "Gold": ("gold", "au", "au_ppm", "au_ppb", "au_pct"),
    "Copper": ("copper", "cu", "cu_ppm", "cu_pct"),
    "Zinc": ("zinc", "zn", "zn_ppm", "zn_pct"),
    "Silver": ("silver", "ag", "ag_ppm", "ag_ppb"),
    "Arsenic": ("arsenic", "as_ppm", "as_pct"),
    "Lead": ("lead", "pb", "pb_ppm", "pb_pct"),
    "Nickel": ("nickel", "ni", "ni_ppm", "ni_pct"),
    "Cobalt": ("cobalt", "co", "co_ppm", "co_pct"),
    "Lithium": ("lithium", "li", "li_ppm", "li_pct"),
    "Iron": ("iron", "fe", "fe_ppm", "fe_pct"),
}


def _token_present(text: str, alias: str) -> bool:
    """Match names and chemical symbols without accidental substring matches."""
    escaped = re.escape(alias.lower())
    return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text.lower()))


def detect_commodities(*values: object) -> list[str]:
    text = " ".join("" if value is None else str(value) for value in values)
    return [
        commodity
        for commodity, aliases in COMMODITY_ALIASES.items()
        if any(_token_present(text, alias) for alias in aliases)
    ]


def commodity_tags(*values: object) -> str:
    detected = detect_commodities(*values)
    return " | ".join(detected) if detected else "Other / non-commodity"


def commodity_mask(series: pd.Series, selected: list[str]) -> pd.Series:
    if not selected:
        return pd.Series(True, index=series.index)
    pattern = "|".join(re.escape(value) for value in selected)
    return series.fillna("").astype(str).str.contains(pattern, case=False, regex=True)


def parse_result_evidence(filename: str, blob: bytes) -> tuple[pd.DataFrame, dict | list | None]:
    """Parse safe result files for display; no query or uploaded code is executed."""
    lower_name = str(filename or "").lower()
    if lower_name.endswith(".csv"):
        return pd.read_csv(BytesIO(blob), nrows=5000), None
    if lower_name.endswith((".json", ".geojson")):
        payload = json.loads(blob.decode("utf-8", errors="strict"))
        if isinstance(payload, list):
            return pd.json_normalize(payload).head(5000), payload
        if isinstance(payload, dict) and isinstance(payload.get("features"), list):
            records = []
            for feature in payload["features"][:5000]:
                if not isinstance(feature, dict):
                    continue
                record = dict(feature.get("properties") or {})
                geometry = feature.get("geometry") or {}
                coordinates = geometry.get("coordinates") or []
                if geometry.get("type") == "Point" and len(coordinates) >= 2:
                    record["longitude"] = coordinates[0]
                    record["latitude"] = coordinates[1]
                records.append(record)
            return pd.DataFrame(records), payload
        if isinstance(payload, dict):
            for key in ("results", "rows", "data", "records"):
                if isinstance(payload.get(key), list):
                    return pd.json_normalize(payload[key]).head(5000), payload
            return pd.json_normalize(payload).head(5000), payload
        return pd.DataFrame(), payload
    return pd.DataFrame(), None

def csv_result_diagnostics(blob: bytes) -> dict:
    """Summarize data-quality signals across the complete uploaded CSV."""
    frame = pd.read_csv(BytesIO(blob))
    numeric = {}

    for column in frame.select_dtypes(include="number").columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        sentinel_count = int(values.eq(-9999).sum())
        negative_count = int(values.lt(0).sum())

        numeric[str(column)] = {
            "sentinel_count": sentinel_count,
            "negative_count": negative_count,
            "other_negative_count": negative_count - sentinel_count,
        }

    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "missing_cells": int(frame.isna().sum().sum()),
        "duplicate_rows": int(frame.duplicated().sum()),
        "numeric_columns": numeric,
    }


def numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [
        column
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column])
    ]


def category_columns(frame: pd.DataFrame, maximum_unique: int = 60) -> list[str]:
    return [
        column
        for column in frame.columns
        if not pd.api.types.is_numeric_dtype(frame[column])
        and 1 < frame[column].nunique(dropna=True) <= maximum_unique
    ]


def commodity_metric_columns(frame: pd.DataFrame) -> list[str]:
    matches = []
    for column in frame.columns:
        lowered = str(column).lower()
        if any(
            _token_present(lowered, alias)
            for aliases in COMMODITY_ALIASES.values()
            for alias in aliases
        ):
            matches.append(column)
    numeric = set(numeric_columns(frame))
    return [column for column in matches if column in numeric]


def coordinate_columns(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    names = {str(column).lower(): column for column in frame.columns}
    latitude = next(
        (names[name] for name in ("latitude", "lat", "y_coord", "northing") if name in names),
        None,
    )
    longitude = next(
        (names[name] for name in ("longitude", "lon", "lng", "x_coord", "easting") if name in names),
        None,
    )
    return latitude, longitude


def friendly_metric(column: str) -> str:
    detected = detect_commodities(column)
    commodity = detected[0] if detected else "Metric"
    unit = ""
    lower = str(column).lower()
    for candidate in ("ppm", "ppb", "pct", "percent", "%"):
        if candidate in lower:
            unit = "%" if candidate in {"pct", "percent", "%"} else candidate
            break
    return f"{commodity} · {column}" + (f" ({unit})" if unit else "")


def prepare_pie_data(
    frame: pd.DataFrame,
    category_column: str,
    metric_column: str | None = None,
    aggregation: str = "Count rows",
    maximum_slices: int = 5,
) -> pd.DataFrame:
    """Build an honest, bounded part-to-whole table for a pie or donut chart."""
    if frame.empty or category_column not in frame.columns:
        return pd.DataFrame(columns=["Category", "Value"])

    working = pd.DataFrame(
        {
            "Category": (
                frame[category_column]
                .fillna("Missing")
                .astype(str)
                .str.strip()
                .replace("", "Missing")
            )
        }
    )
    if aggregation == "Sum selected measure" and metric_column in frame.columns:
        working["Value"] = pd.to_numeric(frame[metric_column], errors="coerce")
        # Negative and zero values cannot be represented honestly as pie slices.
        working = working[working["Value"] > 0]
        grouped = working.groupby("Category", dropna=False)["Value"].sum()
    else:
        grouped = working.groupby("Category", dropna=False).size().rename("Value")

    grouped = grouped[grouped > 0].sort_values(ascending=False)
    maximum_slices = max(2, int(maximum_slices))
    if len(grouped) > maximum_slices:
        head = grouped.head(maximum_slices)
        other = grouped.iloc[maximum_slices:].sum()
        grouped = pd.concat([head, pd.Series({"Other": other})])
    return grouped.rename("Value").rename_axis("Category").reset_index()


def correlation_long(frame: pd.DataFrame, maximum_columns: int = 10) -> pd.DataFrame:
    """Return a tidy correlation matrix for sufficiently variable numeric fields."""
    usable = []
    for column in numeric_columns(frame):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().sum() >= 3 and values.nunique(dropna=True) >= 2:
            usable.append(column)
        if len(usable) >= max(2, int(maximum_columns)):
            break
    if len(usable) < 2:
        return pd.DataFrame(columns=["Measure X", "Measure Y", "Correlation"])
    correlation = frame[usable].apply(pd.to_numeric, errors="coerce").corr()
    return (
        correlation.rename_axis("Measure Y")
        .reset_index()
        .melt(id_vars="Measure Y", var_name="Measure X", value_name="Correlation")
        .dropna(subset=["Correlation"])
    )


def column_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Create a compact, safe profile used by the result explorer."""
    rows = []
    total_rows = len(frame)
    for column in frame.columns:
        series = frame[column]
        numeric = pd.to_numeric(series, errors="coerce")
        is_numeric = pd.api.types.is_numeric_dtype(series)
        row = {
            "Column": str(column),
            "Type": "Numeric" if is_numeric else "Text / category",
            "Non-null": int(series.notna().sum()),
            "Missing %": round(float(series.isna().mean() * 100), 1) if total_rows else 0.0,
            "Unique": int(series.nunique(dropna=True)),
            "Minimum": None,
            "Average": None,
            "Maximum": None,
        }
        if is_numeric and numeric.notna().any():
            row.update(
                {
                    "Minimum": float(numeric.min()),
                    "Average": float(numeric.mean()),
                    "Maximum": float(numeric.max()),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)
