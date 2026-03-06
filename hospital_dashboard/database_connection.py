"""
Layer 1 — Supabase Data Access Layer

This module provides connection to the Supabase PostgreSQL database and
helper functions to fetch hospital tables as pandas DataFrames.
Credentials are loaded from environment variables: SUPABASE_URL, SUPABASE_KEY.
"""

import os
from typing import Optional

import pandas as pd
from supabase import create_client, Client


def _get_client() -> Client:
    """Create and return Supabase client using environment variables."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY must be set in environment variables."
        )
    return create_client(url, key)


def _fetch_table(table_name: str) -> pd.DataFrame:
    """
    Fetch all rows from a Supabase table and return as DataFrame.
    Uses the default row limit; for very large tables consider pagination.
    """
    client = _get_client()
    response = client.table(table_name).select("*").execute()
    return pd.DataFrame(response.data if response.data else [])


def get_patients() -> pd.DataFrame:
    """
    Fetch the patients table from Supabase.
    Returns: DataFrame with patient records (e.g. patient_id, demographics).
    """
    return _fetch_table("patients")


def get_admissions() -> pd.DataFrame:
    """
    Fetch the admissions table from Supabase.
    Returns: DataFrame with admission records (e.g. patient_id, admission_date, discharge_date, department).
    """
    return _fetch_table("admissions")


def get_vitals() -> pd.DataFrame:
    """
    Fetch the vitals table from Supabase.
    Returns: DataFrame with vital sign measurements (e.g. patient_id, recorded_at, metrics).
    """
    return _fetch_table("vitals")


def get_appointments() -> pd.DataFrame:
    """
    Fetch the appointments table from Supabase.
    Returns: DataFrame with appointment records (e.g. patient_id, appointment_date, department, status).
    """
    return _fetch_table("appointments")


def get_icu_beds() -> pd.DataFrame:
    """
    Fetch the icu_beds table from Supabase.
    Returns: DataFrame with ICU bed status (e.g. bed_id, patient_id, occupied, unit).
    """
    return _fetch_table("icu_beds")


def get_risk_scores() -> pd.DataFrame:
    """
    Fetch the risk_scores table from Supabase.
    Returns: DataFrame with pre-computed or stored risk scores (e.g. patient_id, score_type, value).
    """
    return _fetch_table("risk_scores")
