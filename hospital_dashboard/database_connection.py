"""
Layer 1 — Supabase Data Access Layer

This module provides connection to the Supabase PostgreSQL database and
helper functions to fetch hospital tables as pandas DataFrames.
Uses Supabase REST API (no supabase package - avoids build issues on Windows).
Credentials: SUPABASE_URL, SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY).
"""

import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# Find .env: try multiple locations so it works regardless of run directory
_this_dir = Path(__file__).resolve().parent
_env_candidates = [
    Path.cwd() / ".env",           # current working directory
    _this_dir / ".env",            # hospital_dashboard/
    _this_dir.parent / ".env",     # project root (Hackathon/)
]
for env_path in _env_candidates:
    if env_path.exists():
        load_dotenv(env_path)
        break
load_dotenv()  # fallback: cwd (dotenv default)

# Cache: avoid re-fetching same table on every render (TTL 30 seconds)
_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL = 30
_PAGE_SIZE = 5000  # larger pages = fewer HTTP requests


def _get_headers() -> dict:
    """Build headers for Supabase REST API."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) must be set."
        )
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Accept": "application/json",
    }


def _fetch_table(table_name: str, filter_col: str | None = None, filter_val: str | None = None, use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch rows from Supabase via REST API. Uses pagination and optional caching.
    If filter_col/filter_val provided, fetches only matching rows (no cache).
    """
    cache_key = f"{table_name}:{filter_col or ''}:{filter_val or ''}"
    if use_cache and filter_col is None and cache_key in _CACHE:
        ts, df = _CACHE[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return df.copy()

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    base_url = f"{url}/rest/v1/{table_name}"
    headers = _get_headers()
    params = {"select": "*"}
    if filter_col and filter_val:
        params[f"{filter_col}"] = f"eq.{filter_val}"

    all_data = []
    start = 0
    while True:
        headers_copy = {**headers, "Range": f"{start}-{start + _PAGE_SIZE - 1}"}
        resp = requests.get(base_url, headers=headers_copy, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        all_data.extend(data)
        if len(data) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE

    df = pd.DataFrame(all_data)
    if use_cache and filter_col is None:
        _CACHE[cache_key] = (time.time(), df)
    return df


def get_patients() -> pd.DataFrame:
    """Fetch the patients table from Supabase."""
    return _fetch_table("patients")


def get_admissions() -> pd.DataFrame:
    """Fetch the admissions table from Supabase."""
    return _fetch_table("admissions")


def get_vitals() -> pd.DataFrame:
    """Fetch the vitals table from Supabase (cached)."""
    return _fetch_table("vitals")


def get_vitals_for_patient(patient_id: str) -> pd.DataFrame:
    """Fetch vitals for a single patient only (avoids loading 120k+ rows)."""
    return _fetch_table("vitals", filter_col="patient_id", filter_val=str(patient_id), use_cache=False)


def get_appointments() -> pd.DataFrame:
    """Fetch the appointments table from Supabase."""
    return _fetch_table("appointments")


def get_icu_beds() -> pd.DataFrame:
    """Fetch the icu_beds table from Supabase."""
    return _fetch_table("icu_beds")


def get_risk_scores() -> pd.DataFrame:
    """Fetch the risk_scores table from Supabase."""
    return _fetch_table("risk_scores")
