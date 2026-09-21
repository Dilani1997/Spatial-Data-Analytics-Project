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
    return frame
