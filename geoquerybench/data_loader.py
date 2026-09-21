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
