"""Read-only evidence comparison for GeoQueryBench.

Scores are defined ONLY for compatible CSV or JSON tabular results.
No SQL is executed, no review verdicts are modified, and uploaded data is not saved.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
from io import BytesIO
import json
from pathlib import Path
import re

import pandas as pd
import streamlit as st

MAX_COMPARE_BYTES = 10 * 1024 * 1024


def _scalar(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return "<NULL>"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        number = Decimal(raw)
        if number.is_finite():
            return str(number.normalize())
    except InvalidOperation:
        pass
    return raw


def _read_table(raw: bytes, filename: str):
    if len(raw) > MAX_COMPARE_BYTES:
        raise ValueError("Evidence exceeds the 10 MB comparison limit.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(BytesIO(raw), dtype=str, keep_default_na=False)
    if suffix == ".json":
        data = json.loads(raw.decode("utf-8-sig"))
        if isinstance(data, dict):
            for key in ("rows", "results", "data", "features"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ValueError("JSON must contain a list of row objects (or an object with rows/results/data).")
        return pd.DataFrame(data)
    raise ValueError("Only tabular CSV and JSON results support automatic comparison.")


def compare_results(reference: bytes, reference_name: str, actual: bytes, actual_name: str):
    """Order-independent row-multiset F1 and exact-match stats.

    A percentage is withheld if schemas differ, or either table is unreadable.
    """
    expected = _read_table(reference, reference_name)
    observed = _read_table(actual, actual_name)
    exp_cols = [str(c).strip() for c in expected.columns]
    obs_cols = [str(c).strip() for c in observed.columns]
    if len(set(exp_cols)) != len(exp_cols) or len(set(obs_cols)) != len(obs_cols):
        raise ValueError("Duplicate column names prevent a reliable comparison.")
    missing = sorted(set(exp_cols) - set(obs_cols))
    extra = sorted(set(obs_cols) - set(exp_cols))
    if missing or extra:
        return {"measurable": False, "reason": "Output columns differ; comparison withheld.",
                "missing_columns": missing, "extra_columns": extra,
                "expected_rows": len(expected), "actual_rows": len(observed)}
    expected.columns = exp_cols
    observed.columns = obs_cols
    expected = expected.reindex(columns=sorted(exp_cols))
    observed = observed.reindex(columns=sorted(exp_cols))
    def rows(df):
        return Counter(tuple(_scalar(v) for v in row) for row in df.itertuples(index=False, name=None))
    e, a = rows(expected), rows(observed)
    matched = sum((e & a).values())
    n_expected, n_actual = len(expected), len(observed)
    precision = matched / n_actual if n_actual else (1.0 if n_expected == 0 else 0.0)
    recall = matched / n_expected if n_expected else (1.0 if n_actual == 0 else 0.0)
    agreement = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"measurable": True, "score": agreement, "precision": precision,
            "recall": recall, "matched_rows": matched,
            "expected_rows": n_expected, "actual_rows": n_actual,
            "exact": e == a, "missing_columns": [], "extra_columns": []}


def render_result_accuracy(questions, manifest, gold_dir, expected_file, saved_reviews):
    st.markdown("### 📏 Per-query result accuracy")
    st.write("Compare an independently executed query result with its official reference output. "
             "The score is a row-level F1 agreement percentage, **not** SQL text similarity.")
    qids = questions["qid"].astype(str).tolist()
    choice = st.selectbox("Choose query ID", qids, key="result_accuracy_qid")
    sample = questions.loc[questions["qid"].astype(str) == choice].iloc[0]
    st.write("**Original question:**", str(sample.get("question_en", "")))
    matching = saved_reviews.loc[saved_reviews["qid"].astype(str) == choice] if not saved_reviews.empty else pd.DataFrame()
    if not matching.empty:
        votes = matching["verdict"].value_counts()
        st.caption("Saved reviewer decisions: " + ", ".join(
            str(votes.get(k, 0)) + " " + k for k in ("Pass", "Fail", "Needs clarification")))
    official = expected_file(choice, manifest)
    if official is None:
        st.info("No official reference output available for this query. Result accuracy: Not measured.")
        return
    if official.suffix.lower() not in {".csv", ".json"}:
        st.info("Official output is not a tabular CSV/JSON file. Automated numeric accuracy: Not measured.")
        return
    st.caption("Official reference: " + official.name + " (read-only)")
    upload = st.file_uploader("Upload independently executed output (CSV or JSON)", type=["csv", "json"],
                              key="result_accuracy_upload")
    if upload is None:
        st.info("Upload an actual result to calculate this query's accuracy. Current score: Not measured.")
        return
    try:
        result = compare_results(official.read_bytes(), official.name, upload.getvalue(), upload.name)
    except (ValueError, UnicodeError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        st.warning("Result accuracy: Not measured. " + str(exc))
        return
    if not result["measurable"]:
        st.warning(result["reason"])
        st.write("Missing columns:", result["missing_columns"])
        st.write("Additional columns:", result["extra_columns"])
        return
    a, b, c, d = st.columns(4)
    a.metric("Result agreement", f'{result["score"]:.1%}')
    b.metric("Matched rows", result["matched_rows"])
    c.metric("Expected rows", result["expected_rows"])
    d.metric("Actual rows", result["actual_rows"])
    st.write(f'**Row precision:** {result["precision"]:.1%} · **Row recall:** {result["recall"]:.1%}')
    if result["exact"]:
        st.success("The tabular outputs match exactly, ignoring row and column order.")
    else:
        st.warning("The outputs differ. Inspect query logic, data, and missing/extra rows.")
    st.caption("Repeated rows are counted. Comparisons require identical column names; row order is ignored. "
               "Numeric text is normalised, but tolerances for floating-point differences are not applied. "
               "Uploads are processed for comparison only and are not saved as review evidence.")
