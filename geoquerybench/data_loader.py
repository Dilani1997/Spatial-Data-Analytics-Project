"""Dataset discovery, schema normalization and diagnostics. Owner: Sarwesh."""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from review_visuals import commodity_tags
from .config import APP_DIRECTORY, COLUMN_ALIASES, DATA_FILE_CANDIDATES


def clean(value, fallback="Not specified"):
    if value is None or (not isinstance(value, (bytes, bytearray)) and pd.isna(value)):
        return fallback
    text = str(value).strip()
    return text if text else fallback

def resolve_data_file():
    configured = os.getenv("GQB_DATA_FILE", "").strip()
    configured_path = Path(configured).expanduser() if configured else None
    if configured_path and not configured_path.is_absolute():
        configured_path = APP_DIRECTORY / configured_path
    candidates = ([configured_path] if configured_path else []) + DATA_FILE_CANDIDATES
    return next((path for path in candidates if path.exists()), None)

def normalize_questions(frame):
    """Map both the seed file and the client's expanded bilingual file."""
    frame = frame.copy()
    if frame.empty:
        raise ValueError("The dataset is empty.")
    lowered = {str(column).strip().lower(): column for column in frame.columns}
    rename_map = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in frame.columns:
            continue
        for alias in aliases:
            if alias.lower() in lowered:
                rename_map[lowered[alias.lower()]] = canonical
                break
    frame = frame.rename(columns=rename_map)

    if "qid" not in frame.columns:
        frame["qid"] = [f"Q-{number:04d}" for number in range(1, len(frame) + 1)]
    frame["qid"] = frame["qid"].astype(str).str.strip()
    frame = frame[frame["qid"].ne("") & frame["qid"].ne("nan")].copy()
    if frame["qid"].duplicated().any():
        duplicates = frame.loc[frame["qid"].duplicated(), "qid"].unique().tolist()
        raise ValueError(f"Duplicate question IDs found: {', '.join(duplicates[:10])}")

    defaults = {
        "scenario": "Uncategorised", "qtype": "Unknown", "qtype_name": "Unknown",
        "task": "unknown", "difficulty": "unknown", "question_en": "",
        "question_zh": "", "gold_code": "", "notes": "",
        "rewrite_source": "", "expected_output": "",
    }
    for column, default in defaults.items():
        if column not in frame.columns:
            frame[column] = default
        frame[column] = frame[column].fillna(default)

    # At least one language must contain the question text.
    no_question = frame["question_en"].astype(str).str.strip().eq("") & frame[
        "question_zh"
    ].astype(str).str.strip().eq("")
    if no_question.any():
        raise ValueError(f"{int(no_question.sum())} rows contain neither English nor Chinese question text.")
    frame["commodity_tags"] = frame.apply(
        lambda item: commodity_tags(
            item["question_en"], item["question_zh"], item["gold_code"],
            item["notes"], item["qtype_name"],
        ),
        axis=1,
    )
    return frame

def dataset_diagnostics(frame):
    text_columns = [
        "question_en", "question_zh", "gold_code", "notes", "expected_output",
    ]
    missing = {
        column: int(frame[column].astype(str).str.strip().eq("").sum())
        for column in text_columns
    }
    return {
        "rows": len(frame),
        "duplicate_ids": int(frame["qid"].duplicated().sum()),
        "missing": missing,
        "scenario_count": int(frame["scenario"].nunique()),
        "task_count": int(frame["task"].nunique()),
        "bilingual_complete": int(
            (
                frame["question_en"].astype(str).str.strip().ne("")
                & frame["question_zh"].astype(str).str.strip().ne("")
            ).sum()
        ),
    }

@st.cache_data
def load_questions(path, modified_time):
    del modified_time  # Included in the cache key so replacing the file refreshes the app.
    return normalize_questions(pd.read_csv(path, encoding="utf-8-sig"))


# --- Expanded 824-question workspace helpers (2026-09 update) ---
EXPANDED_REQUIRED_COLUMNS = ("qid", "question_en", "question_zh", "gold_code")
DEFAULT_RESULT_EXTENSIONS = frozenset({".csv", ".txt", ".json", ".geojson", ".png", ".jpg", ".jpeg"})


def load_expanded_questions(path):
    """Load the client expanded bilingual dataset using the stricter live-workspace rules.

    Unlike the legacy normalizer, the expanded dataset requires both English and Chinese
    question text for every row and preserves all source columns as strings.
    """
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    lowered = {str(column).strip().lower(): column for column in frame.columns}
    rename_map = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in frame.columns:
            continue
        for alias in aliases:
            key = alias.lower()
            if key in lowered:
                rename_map[lowered[key]] = canonical
                break
    frame = frame.rename(columns=rename_map)
    missing = [column for column in EXPANDED_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))

    frame["qid"] = frame["qid"].astype(str).str.strip()
    if frame["qid"].eq("").any() or frame["qid"].duplicated().any():
        raise ValueError("Missing or duplicate question IDs: fix the supplied CSV before reviewing.")
    if frame["question_en"].astype(str).str.strip().eq("").any() or frame[
        "question_zh"
    ].astype(str).str.strip().eq("").any():
        raise ValueError("Every expanded case must contain English and Chinese text.")
    return frame


