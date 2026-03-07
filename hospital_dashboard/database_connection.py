"""
Layer 1 — Data Repository

Handles all Supabase database queries. No business logic or calculations.
Fetches hospital tables as pandas DataFrames via Supabase REST API
(no supabase package). Credentials: SUPABASE_URL, SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY).
"""

import os
import threading
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# Find .env: try multiple locations so it works regardless of run directory
_this_dir = Path(__file__).resolve().parent
_env_candidates = [
    Path.cwd() / ".env",
    _this_dir / ".env",
    _this_dir.parent / ".env",
]
for env_path in _env_candidates:
    if env_path.exists():
        load_dotenv(env_path)
        break
load_dotenv()

# Cache: avoid re-fetching same table on every render (TTL 30 seconds)
_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL = 30
_PAGE_SIZE = 5000
# Cap total rows per query to avoid unbounded fetch
_MAX_ROWS = 10000

# When True, print every query + row count + time in ms (set DEBUG=1 in env)
DB_DEBUG = os.environ.get("DEBUG", "").strip().lower() in ("1", "true", "yes")

from dashboard_log import DEBUG as _DEBUG, log as _log, log_error as _log_error


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


def normalize_dates(df: pd.DataFrame, date_columns: list[str] | None = None) -> pd.DataFrame:
    """
    Convert date-like columns to pd.Timestamp. If date_columns is None,
    infers columns with 'date', 'time', 'at', 'timestamp' in name.
    """
    if df is None or df.empty:
        return df
    df = df.copy()
    if date_columns is None:
        date_columns = [
            c for c in df.columns
            if isinstance(c, str) and any(
                x in c.lower() for x in ("date", "time", "_at", "timestamp", "recorded")
            )
        ]
    for c in date_columns:
        if c in df.columns:
            try:
                df[c] = pd.to_datetime(df[c], errors="coerce", format="mixed")
            except Exception:
                pass
    return df


def test_connection() -> bool:
    """Return True if Supabase is reachable and credentials work."""
    try:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
        if not url or not key:
            return False
        headers = _get_headers()
        # Minimal request: fetch 0 rows from a small table
        resp = requests.get(
            f"{url}/rest/v1/patients",
            headers={**headers, "Range": "0-0"},
            params={"select": "patient_id"},
            timeout=5,
        )
        return resp.status_code in (200, 206)
    except Exception:
        return False


def _fetch_table(
    table_name: str,
    filter_col: str | None = None,
    filter_val: str | None = None,
    use_cache: bool = True,
    max_rows: int = _MAX_ROWS,
) -> pd.DataFrame:
    """
    Fetch rows from Supabase via REST API. Uses pagination and optional caching.
    Stops after max_rows rows. If filter_col/filter_val provided, no cache.
    """
    cache_key = f"{table_name}:{filter_col or ''}:{filter_val or ''}"
    if use_cache and filter_col is None and cache_key in _CACHE:
        ts, df = _CACHE[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return df.copy()

    t0 = time.perf_counter()
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    base_url = f"{url}/rest/v1/{table_name}"
    headers = _get_headers()
    params = {"select": "*"}
    if filter_col and filter_val:
        params[f"{filter_col}"] = f"eq.{filter_val}"

    all_data = []
    start = 0
    while start < max_rows:
        end = min(start + _PAGE_SIZE, start + max_rows - len(all_data))
        if end <= start:
            break
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
        if len(all_data) >= max_rows:
            break

    df = pd.DataFrame(all_data)
    df = normalize_dates(df)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    _log("Supabase", f"query {table_name}", rows=len(df), columns=list(df.columns)[:20])
    if len(df) == 0:
        _log("Supabase", f"{table_name} returned 0 rows")
    if DB_DEBUG:
        print(f"[DB_DEBUG] {table_name} rows={len(df)} time_ms={elapsed_ms:.0f}")
    if use_cache and filter_col is None:
        _CACHE[cache_key] = (time.time(), df)
    return df


def get_patients() -> pd.DataFrame:
    """Fetch the patients table from Supabase (capped). Reads from shared cache."""
    out = DATA_CACHE.get("patients", _fetch_table, "patients", max_rows=_MAX_ROWS)
    return out if out is not None else pd.DataFrame()


def get_admissions() -> pd.DataFrame:
    """Fetch the admissions table from Supabase (capped). Reads from shared cache."""
    out = DATA_CACHE.get("admissions", _fetch_table, "admissions", max_rows=_MAX_ROWS)
    return out if out is not None else pd.DataFrame()


def get_vitals() -> pd.DataFrame:
    """Fetch the vitals table from Supabase (capped). Reads from shared cache."""
    out = DATA_CACHE.get("vitals", _fetch_table, "vitals", max_rows=_MAX_ROWS)
    return out if out is not None else pd.DataFrame()


def get_vitals_for_patient(patient_id: str) -> pd.DataFrame:
    """Fetch vitals for a single patient only (avoids loading 120k+ rows)."""
    return _fetch_table(
        "vitals",
        filter_col="patient_id",
        filter_val=str(patient_id),
        use_cache=False,
        max_rows=5000,
    )


def get_appointments() -> pd.DataFrame:
    """Fetch the appointments table from Supabase (capped). Reads from shared cache."""
    out = DATA_CACHE.get("appointments", _fetch_table, "appointments", max_rows=_MAX_ROWS)
    return out if out is not None else pd.DataFrame()


def get_icu_beds() -> pd.DataFrame:
    """Fetch the icu_beds table from Supabase. Reads from shared cache."""
    out = DATA_CACHE.get("icu_beds", _fetch_table, "icu_beds", max_rows=500)
    return out if out is not None else pd.DataFrame()


def get_risk_scores() -> pd.DataFrame:
    """Fetch the risk_scores table from Supabase (capped). Reads from shared cache."""
    out = DATA_CACHE.get("risk_scores", _fetch_table, "risk_scores", max_rows=_MAX_ROWS)
    return out if out is not None else pd.DataFrame()


# ─── Single in-memory cache for all Supabase data ─────────────────────────
class _DataCache:
    """
    Single in-memory cache for all Supabase data.
    Fetches everything once, serves all render functions from memory.
    Refreshes every CACHE_TTL seconds.
    """

    CACHE_TTL = 60  # seconds

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}
        self._timestamps = {}

    def get(self, key: str, fetch_fn, *args, **kwargs):
        now = time.time()
        with self._lock:
            if key not in self._cache or (now - self._timestamps.get(key, 0)) > self.CACHE_TTL:
                try:
                    t0 = time.time()
                    self._cache[key] = fetch_fn(*args, **kwargs)
                    elapsed = (time.time() - t0) * 1000
                    print(f"[Cache] {key}: fetched in {elapsed:.0f}ms")
                except Exception as e:
                    print(f"[Cache] {key}: fetch failed: {e}")
                    if key not in self._cache:
                        self._cache[key] = None
                self._timestamps[key] = now
        return self._cache.get(key)

    def invalidate(self, key: str = None):
        with self._lock:
            if key:
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
            else:
                self._cache.clear()
                self._timestamps.clear()

    def warm(self):
        """
        Pre-fetch all tables at startup in parallel threads.
        Call this once when app starts so first page load is instant.
        """
        import concurrent.futures

        tables = [
            ("patients", get_patients),
            ("admissions", get_admissions),
            ("icu_beds", get_icu_beds),
            ("risk_scores", get_risk_scores),
            ("appointments", get_appointments),
            ("vitals", get_vitals),
        ]
        print("[Cache] Warming cache in background...")
        t0 = time.time()

        def _fetch(name, fn):
            fn()

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            futures = [ex.submit(_fetch, name, fn) for name, fn in tables]
            concurrent.futures.wait(futures, timeout=30)

        elapsed = (time.time() - t0) * 1000
        print(f"[Cache] Warm complete in {elapsed:.0f}ms")


# Global cache instance
DATA_CACHE = _DataCache()
