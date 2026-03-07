"""
Decision support — historical trend data from Supabase.

Provides get_trend_data(metric_name) for time-series charts.
Uses database_connection for all Supabase access; no business logic.
"""

from typing import Literal

import pandas as pd

from database_connection import (
    get_admissions,
    get_appointments,
    get_icu_beds,
    get_risk_scores,
)
from hospital_analytics import get_data_reference_date

MetricName = Literal["icu_occupancy", "readmission_risk", "no_show"]


def _safe_date_col(df: pd.DataFrame, candidates: list[str]):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def get_trend_data(
    metric_name: str,
    *,
    hours_24: bool = False,
    days_7: bool = True,
) -> pd.DataFrame:
    """
    Fetch historical trend data for the given metric from Supabase-backed tables.

    Supported metric_name: "icu_occupancy", "readmission_risk", "no_show".

    Returns DataFrame with columns:
      - date (datetime or date)
      - value (float or int; for ICU 0–100, for readmission/no_show counts)

    hours_24: if True, attempt 24-hour granularity (only when data has time).
    days_7: if True, last 7 days; otherwise last 30 days.
    """
    ref = get_data_reference_date()
    if not isinstance(ref, pd.Timestamp):
        ref = pd.Timestamp(ref)
    window_days = 7 if days_7 else 30
    cutoff = ref - pd.Timedelta(days=window_days)

    if metric_name == "icu_occupancy":
        return _trend_icu_occupancy(ref, cutoff)
    if metric_name == "readmission_risk":
        return _trend_readmission_risk(ref, cutoff)
    if metric_name == "no_show":
        return _trend_no_show(ref, cutoff)
    return pd.DataFrame(columns=["date", "value"])


def _trend_icu_occupancy(ref: pd.Timestamp, cutoff: pd.Timestamp) -> pd.DataFrame:
    """
    ICU occupancy trend: proxy from admissions/discharges (no historical ICU snapshot).
    Daily value = estimated occupancy % (0–100) from cumulative in/out flow.
    """
    admissions = get_admissions()
    if admissions is None or admissions.empty:
        return pd.DataFrame(columns=["date", "value"])

    adate = _safe_date_col(admissions, ["admission_date", "admit_date", "start_date", "date"])
    ddate = _safe_date_col(admissions, ["discharge_date", "discharge_at", "end_date"])
    if not adate:
        return pd.DataFrame(columns=["date", "value"])

    df = admissions.copy()
    df[adate] = pd.to_datetime(df[adate], errors="coerce")
    df = df.dropna(subset=[adate])
    df = df[df[adate] >= cutoff]
    if df.empty:
        return pd.DataFrame(columns=["date", "value"])

    beds = get_icu_beds()
    total_beds = 50
    if beds is not None and not beds.empty:
        total_beds = len(beds)

    df["date"] = df[adate].dt.date
    daily_adm = df.groupby("date").size().reset_index(name="admissions")

    if ddate and ddate in admissions.columns:
        adm2 = admissions.copy()
        adm2[ddate] = pd.to_datetime(adm2[ddate], errors="coerce")
        adm2 = adm2.dropna(subset=[ddate])
        adm2 = adm2[adm2[ddate] >= cutoff]
        adm2["date"] = adm2[ddate].dt.date
        daily_disch = adm2.groupby("date").size()
        daily_adm["discharges"] = daily_adm["date"].map(lambda d: daily_disch.get(d, 0)).astype(int)
    else:
        daily_adm["discharges"] = 0

    daily_adm["date"] = pd.to_datetime(daily_adm["date"])
    daily_adm = daily_adm.sort_values("date")
    # Proxy: rolling net (admissions - discharges) as occupancy pressure
    daily_adm["net"] = daily_adm["admissions"] - daily_adm["discharges"]
    daily_adm["cumulative_net"] = daily_adm["net"].cumsum()
    daily_adm["value"] = (daily_adm["cumulative_net"] / total_beds * 100).clip(0, 100).round(1)
    out = daily_adm[["date", "value"]].copy()
    return out


def _trend_readmission_risk(ref: pd.Timestamp, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Daily count of high-risk patients (e.g. discharged that day with readmission_risk >= 0.6)."""
    risk_df = get_risk_scores()
    admissions = get_admissions()
    if admissions is None or admissions.empty:
        return pd.DataFrame(columns=["date", "value"])
    adate = _safe_date_col(admissions, ["admission_date", "admit_date", "start_date", "date"])
    ddate = _safe_date_col(admissions, ["discharge_date", "discharge_at", "end_date"])
    pid_col = "patient_id" if "patient_id" in admissions.columns else admissions.columns[0]
    if not adate:
        return pd.DataFrame(columns=["date", "value"])

    high_risk_ids = set()
    if risk_df is not None and not risk_df.empty and "readmission_risk" in risk_df.columns and "patient_id" in risk_df.columns:
        rr = pd.to_numeric(risk_df["readmission_risk"], errors="coerce").fillna(0)
        if rr.max() > 1:
            rr = rr / 100.0
        high_risk_ids = set(risk_df.loc[rr >= 0.6, "patient_id"].astype(str).unique())

    df = admissions.copy()
    date_col = ddate if ddate and ddate in df.columns else adate
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    df = df[df[date_col] >= cutoff]
    df["date"] = df[date_col].dt.date
    df["patient_id"] = df[pid_col].astype(str)
    df["high_risk"] = df["patient_id"].isin(high_risk_ids)
    daily = df.groupby("date")["high_risk"].sum().reset_index()
    daily.columns = ["date", "value"]
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.sort_values("date")


def _trend_no_show(ref: pd.Timestamp, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Daily count of no-show appointments."""
    appointments = get_appointments()
    if appointments is None or appointments.empty:
        return pd.DataFrame(columns=["date", "value"])
    date_col = _safe_date_col(appointments, ["appointment_date", "scheduled_date", "date", "appointment_at"])
    if not date_col:
        return pd.DataFrame(columns=["date", "value"])
    no_show_col = "no_show" if "no_show" in appointments.columns else None
    if not no_show_col:
        status_col = next((c for c in appointments.columns if "status" in c.lower() or "outcome" in c.lower()), None)
        if status_col:
            appointments = appointments.copy()
            appointments["no_show"] = appointments[status_col].astype(str).str.lower().str.contains("no-show|noshow|cancel", na=False, regex=True)
        else:
            appointments = appointments.copy()
            appointments["no_show"] = False
        no_show_col = "no_show"

    df = appointments.copy()
    df["_dt"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["_dt"])
    df = df[df["_dt"] >= cutoff]
    df["date"] = df["_dt"].dt.date
    daily = df.groupby("date")[no_show_col].sum().reset_index()
    daily.columns = ["date", "value"]
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.sort_values("date")
