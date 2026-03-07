"""
Layer 2 — Analytics Engine

All calculations and data transformations. Uses the data repository for Supabase
queries only. Can run independently for debugging (python -m hospital_analytics).

- ICU occupancy
- Readmission risk filtering
- No-show rate aggregation
- Admission trends
- Patient history

Hospital profile: ~5000 patients, 50 ICU beds. High readmission ≥ 0.6; ICU risk ≥ 90%.
"""

from typing import Any, Optional

import pandas as pd

from constants import (
    PATIENT_ID_COL,
    READMISSION_RISK_COL,
    ADMISSION_DATE_COL,
    DISCHARGE_DATE_COL,
    DEPARTMENT_COL,
    HIGH_RISK_EMPTY_COLS,
    DEPT_NO_SHOW_EMPTY_COLS,
    TREND_EMPTY_COLS,
)

# Operational thresholds (hospital assumptions)
READMISSION_RISK_THRESHOLD = 0.6   # Patients above this are flagged in the system
ICU_HIGH_RISK_OCCUPANCY = 0.9     # ICU occupancy ≥ 90% = high operational risk

from dashboard_log import log as _log, log_error as _log_error, log_empty as _log_empty

from database_connection import (
    get_patients,
    get_admissions,
    get_vitals,
    get_vitals_for_patient,
    get_appointments,
    get_icu_beds,
    get_risk_scores,
)


def _log_df(stage: str, message: str, df: pd.DataFrame) -> None:
    """Log DataFrame shape and column names for analytics debugging."""
    rows = 0 if df is None or df.empty else len(df)
    cols = list(df.columns) if df is not None and not df.empty else []
    _log(stage, message, rows=rows, columns=cols)


def _safe_date_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return first existing column name from candidates, or None."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _get_data_reference_date(df: pd.DataFrame, date_col: str) -> pd.Timestamp:
    """
    Returns the most recent date in the given DataFrame as the reference 'today'.
    Used when a single table is already loaded. For global ref, use get_data_reference_date().
    """
    if df is None or df.empty or date_col not in df.columns:
        return pd.Timestamp.now()
    latest = pd.to_datetime(df[date_col], errors="coerce").max()
    if pd.isna(latest):
        return pd.Timestamp.now()
    return latest


def get_data_reference_date() -> pd.Timestamp:
    """
    Global data reference date: the most recent timestamp in admissions or appointments.
    Use this as the system's "today" so the dashboard works with historical datasets
    (e.g. 2023-01-01 to 2024-08-23) instead of the real current date.
    Falls back to pd.Timestamp.now() only if no dates exist in either table.
    """
    candidates = []
    admissions = get_admissions()
    if admissions is not None and not admissions.empty:
        adate = _safe_date_col(admissions, ["admission_date", "admit_date", "start_date", "date"])
        if adate:
            ser = pd.to_datetime(admissions[adate], errors="coerce")
            latest = ser.max()
            if pd.notna(latest):
                candidates.append(latest)
    appointments = get_appointments()
    if appointments is not None and not appointments.empty:
        adate = _safe_date_col(appointments, ["appointment_date", "scheduled_date", "date", "appointment_at"])
        if adate:
            ser = pd.to_datetime(appointments[adate], errors="coerce")
            latest = ser.max()
            if pd.notna(latest):
                candidates.append(latest)
    if not candidates:
        _log("Analytics", "get_data_reference_date: no dates in admissions/appointments, using now()")
        return pd.Timestamp.now()
    ref = max(candidates)
    _log("Analytics", "get_data_reference_date", ref=str(ref))
    return ref


def get_total_patients() -> int:
    """
    Return total number of distinct patients in the system.
    """
    patients = get_patients()
    _log_df("Analytics", "get_total_patients (patients table)", patients)
    if patients is None or patients.empty:
        _log_empty("Analytics", "get_total_patients (no patients)", 0)
        return 0
    if "patient_id" in patients.columns:
        n = int(patients["patient_id"].nunique())
    else:
        n = len(patients)
    _log("Analytics", "get_total_patients result", total_patients=n)
    return n


def get_icu_occupancy() -> dict[str, Any]:
    """
    Return ICU occupancy metrics: total beds, occupied beds, occupancy rate.
    Assumes icu_beds has columns like bed_id, occupied (or status), and optionally unit.
    """
    beds = get_icu_beds()
    _log_df("Analytics", "compute_icu_occupancy (icu_beds)", beds)
    if beds is None or beds.empty:
        _log("Analytics", "compute_icu_occupancy result", total=0, occupied=0, rate=0.0, high_operational_risk=False)
        return {"total": 0, "occupied": 0, "rate": 0.0, "high_operational_risk": False}

    occupied_col = "occupied" if "occupied" in beds.columns else None
    if not occupied_col and "status" in beds.columns:
        occupied_col = "status"

    total = len(beds)
    if occupied_col:
        if beds[occupied_col].dtype == bool:
            occupied = int(beds[occupied_col].sum())
        else:
            occupied = int((beds[occupied_col].astype(str).str.lower().isin(("true", "1", "occupied", "yes"))).sum())
    else:
        # Assume patient_id present means occupied
        pid_col = "patient_id" if "patient_id" in beds.columns else None
        occupied = int(beds[pid_col].notna().sum()) if pid_col else 0

    rate = (occupied / total) if total else 0.0
    result = {
        "total": total,
        "occupied": occupied,
        "rate": round(rate, 4),
        "high_operational_risk": rate >= ICU_HIGH_RISK_OCCUPANCY,  # ≥90% per hospital assumption
    }
    _log("Analytics", "compute_icu_occupancy result", **result)
    return result


def compute_icu_occupancy() -> dict[str, Any]:
    """Public API: ICU occupancy metrics. Same as get_icu_occupancy()."""
    return get_icu_occupancy()


def get_system_strain() -> dict[str, Any]:
    """
    Single call that returns all Command Center strain metrics. Use this instead of
    6 separate calls so KPIs and AI use identical data.
    Returns: icu_rate (0-1), readmit_rate (0-1), noshow_rate (0-1), strain_score (0-100),
    strain_level ('normal'|'elevated'|'critical'), discharge_pending (int),
    admissions_today (int), discharges_today (int), total_patients (int), icu_total (int),
    icu_occupied (int), high_readmission_count (int), likely_no_show_count (int).
    """
    icu = get_icu_occupancy()
    total_patients = get_total_patients()
    high_readmission = get_high_readmission_patients(limit=500)
    no_shows = get_likely_no_shows(days_ahead=1)
    admissions = get_admissions()
    if admissions is None:
        admissions = pd.DataFrame()

    icu_total = icu.get("total") or 0
    icu_occupied = icu.get("occupied") or 0
    icu_rate = (icu.get("rate") or 0.0)
    high_readmission_count = len(high_readmission)  # get_high_readmission_patients already returns distinct patients
    likely_no_show_count = len(no_shows)
    readmit_rate = (high_readmission_count / total_patients) if total_patients else 0.0
    noshow_rate = min(1.0, (likely_no_show_count / max(total_patients * 0.1, 1))) if total_patients else 0.0

    strain_score = (icu_rate * 0.4 + readmit_rate * 0.35 + noshow_rate * 0.25) * 100
    strain_score = min(100.0, max(0.0, strain_score))
    if strain_score < 40:
        strain_level = "normal"
    elif strain_score <= 70:
        strain_level = "elevated"
    else:
        strain_level = "critical"

    adate = _safe_date_col(admissions, [ADMISSION_DATE_COL, "admit_date", "start_date", "date"])
    ddate = _safe_date_col(admissions, [DISCHARGE_DATE_COL, "discharge_at", "end_date"])
    expdate = _safe_date_col(admissions, ["expected_discharge_date", "expected_discharge", "planned_discharge"])
    ref = get_data_reference_date()
    ref_date = ref.date() if hasattr(ref, "date") else ref
    discharge_pending = 0
    admissions_today = 0
    discharges_today = 0
    if admissions is not None and not admissions.empty and adate:
        adm = admissions.copy()
        adm[adate] = pd.to_datetime(adm[adate], errors="coerce")
        admissions_today = int((adm[adate].dt.date == ref_date).sum())
        if ddate and ddate in adm.columns:
            adm[ddate] = pd.to_datetime(adm[ddate], errors="coerce")
            discharges_today = int((adm[ddate].dt.date == ref_date).sum())
        if expdate and expdate in adm.columns and ddate and ddate in adm.columns:
            adm[expdate] = pd.to_datetime(adm[expdate], errors="coerce")
            still_present = adm[ddate].isna() | (adm[ddate].dt.date > ref_date)
            discharge_pending = int((still_present & adm[expdate].notna() & (adm[expdate].dt.date < ref_date)).sum())

    trend = get_admissions_trend(days=7)
    dept_no_show = get_department_no_show_rates()
    admissions_trend_records = trend.to_dict(orient="records") if not trend.empty else []
    department_no_show_records = dept_no_show.head(10).to_dict(orient="records") if not dept_no_show.empty else []

    return {
        "icu_rate": round(icu_rate, 4),
        "readmit_rate": round(readmit_rate, 4),
        "noshow_rate": round(noshow_rate, 4),
        "strain_score": round(strain_score, 1),
        "strain_level": strain_level,
        "discharge_pending": discharge_pending,
        "admissions_today": admissions_today,
        "discharges_today": discharges_today,
        "total_patients": total_patients,
        "icu_total": icu_total,
        "icu_occupied": icu_occupied,
        "high_readmission_count": high_readmission_count,
        "likely_no_show_count": likely_no_show_count,
        "admissions_trend_records": admissions_trend_records,
        "department_no_show_records": department_no_show_records,
        "data_as_of": ref_date.strftime("%b %d, %Y"),
    }


# Display columns for high-risk table (dashboard)
_HIGH_RISK_DISPLAY_COLS = [PATIENT_ID_COL, READMISSION_RISK_COL, "admission_count"]


def _empty_high_risk_df() -> pd.DataFrame:
    """Return empty DataFrame with correct columns for high-risk contract."""
    return pd.DataFrame(columns=HIGH_RISK_EMPTY_COLS)


def get_high_risk_patients(limit: int = 20) -> pd.DataFrame:
    """
    Return patients flagged with high 30-day readmission risk (≥ READMISSION_RISK_THRESHOLD),
    sorted by risk, top N. Uses risk_scores when available, else derives from admissions.
    Returns DataFrame with display-friendly columns when possible.
    """
    return get_high_readmission_patients(limit=limit)


def get_high_readmission_patients(limit: int = 20) -> pd.DataFrame:
    """
    Return patients flagged with high 30-day readmission risk (≥ READMISSION_RISK_THRESHOLD),
    sorted by risk, top N. Uses risk_scores when available, else derives from admissions.
    Database column: readmission_risk (numeric). Raises on fetch/processing errors.
    """
    _rs = get_risk_scores()
    risk_df = _rs if _rs is not None else pd.DataFrame()
    _pt = get_patients()
    patients = _pt if _pt is not None else pd.DataFrame()
    _adm = get_admissions()
    admissions = _adm if _adm is not None else pd.DataFrame()

    _log_df("Analytics", "get_high_risk_patients (risk_scores)", risk_df)
    _log("Analytics", "get_high_risk_patients inputs", risk_rows=len(risk_df), risk_columns=list(risk_df.columns))

    def _coerce_risk(series):
        return pd.to_numeric(series, errors="coerce").fillna(0)

    # Schema with readmission_risk column (matches Supabase risk_scores.readmission_risk)
    if not risk_df.empty and READMISSION_RISK_COL in risk_df.columns and PATIENT_ID_COL in risk_df.columns:
        risk_df = risk_df.copy()
        risk_df[READMISSION_RISK_COL] = _coerce_risk(risk_df[READMISSION_RISK_COL])
        # Normalize to 0.0-1.0 if stored as 0-100
        if risk_df[READMISSION_RISK_COL].max() > 1.0:
            risk_df[READMISSION_RISK_COL] = risk_df[READMISSION_RISK_COL] / 100.0
        out = risk_df[risk_df[READMISSION_RISK_COL] >= READMISSION_RISK_THRESHOLD].copy()
        out = out.drop_duplicates(subset=[PATIENT_ID_COL], keep="first")
        _log("HighRisk", f"filter readmission_risk>={READMISSION_RISK_THRESHOLD}", after_filter=len(out))
        if out.empty:
            _log_empty("HighRisk", "High readmission query", 0)
            return _empty_high_risk_df()
        out = out.sort_values(READMISSION_RISK_COL, ascending=False).head(limit)
        if not patients.empty and PATIENT_ID_COL in patients.columns:
            out = out.merge(patients, on=PATIENT_ID_COL, how="left", suffixes=("", "_y"))
            out = out[[c for c in out.columns if not c.endswith("_y")]]
        # Trim to display columns if we have many
        prefer = [c for c in _HIGH_RISK_DISPLAY_COLS if c in out.columns]
        if prefer and len(out.columns) > len(prefer):
            out = out[prefer]
        _log_df("Analytics", "get_high_risk_patients result", out)
        return out

    # Alternative schema: score_type + value
    if not risk_df.empty and "score_type" in risk_df.columns and PATIENT_ID_COL in risk_df.columns:
        readmission = risk_df[risk_df["score_type"].astype(str).str.lower().str.contains("readmission", na=False)]
        if not readmission.empty and PATIENT_ID_COL in readmission.columns:
            value_col = "value" if "value" in readmission.columns else "score"
            if value_col not in readmission.columns:
                num_cols = readmission.select_dtypes(include="number").columns
                value_col = num_cols[0] if len(num_cols) > 0 else None
            if value_col:
                out = readmission.groupby(PATIENT_ID_COL)[value_col].max().reset_index()
                out = out.rename(columns={value_col: READMISSION_RISK_COL})
                out[READMISSION_RISK_COL] = _coerce_risk(out[READMISSION_RISK_COL])
                if out[READMISSION_RISK_COL].max() > 1.0:
                    out[READMISSION_RISK_COL] = out[READMISSION_RISK_COL] / 100.0
                out = out[out[READMISSION_RISK_COL] >= READMISSION_RISK_THRESHOLD]
                if out.empty:
                    _log_empty("HighRisk", "alternative schema filter", 0)
                    return _empty_high_risk_df()
                out = out.sort_values(READMISSION_RISK_COL, ascending=False).head(limit)
                if not patients.empty and PATIENT_ID_COL in patients.columns:
                    out = out.merge(patients, on=PATIENT_ID_COL, how="left", suffixes=("", "_y"))
                    out = out[[c for c in out.columns if not c.endswith("_y")]]
                prefer = [c for c in _HIGH_RISK_DISPLAY_COLS if c in out.columns]
                if prefer and len(out.columns) > len(prefer):
                    out = out[prefer]
                _log_df("Analytics", "get_high_risk_patients result (alt schema)", out)
                return out

    # Fallback: use admission count as proxy
    if not admissions.empty and PATIENT_ID_COL in admissions.columns:
        counts = admissions.groupby(PATIENT_ID_COL).size().reset_index(name="admission_count")
        max_count = counts["admission_count"].max()
        counts[READMISSION_RISK_COL] = (counts["admission_count"] / max_count).clip(0, 1) if max_count else 0
        counts = counts[counts[READMISSION_RISK_COL] >= READMISSION_RISK_THRESHOLD]
        if counts.empty:
            _log_empty("HighRisk", "fallback admission proxy", 0)
            return _empty_high_risk_df()
        counts = counts.sort_values(READMISSION_RISK_COL, ascending=False).head(limit)
        if not patients.empty and PATIENT_ID_COL in patients.columns:
            counts = counts.merge(patients, on=PATIENT_ID_COL, how="left", suffixes=("", "_y"))
            counts = counts[[c for c in counts.columns if not c.endswith("_y")]]
        prefer = [c for c in _HIGH_RISK_DISPLAY_COLS if c in counts.columns]
        if prefer and len(counts.columns) > len(prefer):
            counts = counts[prefer + [c for c in counts.columns if c not in prefer]][prefer]
        _log_df("Analytics", "get_high_risk_patients result (fallback)", counts)
        return counts

    _log_empty("HighRisk", "no matching schema", 0)
    return _empty_high_risk_df()


def get_likely_no_shows(days_ahead: int = 1) -> pd.DataFrame:
    """
    Return appointments in the next N days that are likely no-shows.
    Uses risk_scores when available (no_show risk), otherwise returns upcoming appointments.
    If no upcoming appointments match, returns historical no-shows from last 30 days as fallback.
    """
    appointments = get_appointments()
    _log_df("Analytics", "get_likely_no_shows (appointments)", appointments)
    if appointments is None or appointments.empty:
        return pd.DataFrame()

    date_col = _safe_date_col(appointments, ["appointment_date", "scheduled_date", "date", "appointment_at"])
    if not date_col:
        return pd.DataFrame()

    appointments = appointments.copy()
    appointments["_dt"] = pd.to_datetime(appointments[date_col], errors="coerce")
    appointments = appointments.dropna(subset=["_dt"])
    appointments["appt_date_only"] = appointments["_dt"].dt.date

    ref = get_data_reference_date()
    today = ref.date() if hasattr(ref, "date") else ref
    target = (ref + pd.Timedelta(days=days_ahead)).date() if hasattr(ref, "date") else ref
    mask_tomorrow = appointments["appt_date_only"] == target
    n_matches = int(mask_tomorrow.sum())
    _log("Analytics", "get_likely_no_shows", data_ref_date=str(today), target_date=str(target), target_matches=n_matches)

    # Primary: target day's appointments
    if n_matches > 0:
        upcoming = appointments.loc[mask_tomorrow].copy()
        upcoming = upcoming.drop(columns=["_dt", "appt_date_only"], errors="ignore")
        risk_df = get_risk_scores()
        # Schema with no_show_risk column (our Supabase schema)
        if not risk_df.empty and "no_show_risk" in risk_df.columns and "patient_id" in risk_df.columns:
            no_show_risk = risk_df[["patient_id", "no_show_risk"]].copy()
            upcoming = upcoming.merge(no_show_risk, on="patient_id", how="left")
            upcoming["no_show_risk"] = upcoming["no_show_risk"].fillna(0)
            upcoming = upcoming.sort_values("no_show_risk", ascending=False)
            _log_df("Analytics", "get_likely_no_shows result", upcoming)
            return upcoming
        # Alternative schema: score_type + value
        if not risk_df.empty and "score_type" in risk_df.columns:
            no_show = risk_df[risk_df["score_type"].astype(str).str.lower().str.contains("no_show|noshow", na=False, regex=True)]
            if not no_show.empty and "patient_id" in no_show.columns:
                value_col = "value" if "value" in no_show.columns else "score"
                if value_col not in no_show.columns and no_show.select_dtypes(include="number").columns.any():
                    value_col = no_show.select_dtypes(include="number").columns[0]
                if value_col:
                    no_show_risk = no_show.groupby("patient_id")[value_col].max().reset_index()
                    no_show_risk = no_show_risk.rename(columns={value_col: "no_show_risk"})
                    upcoming = upcoming.merge(no_show_risk, on="patient_id", how="left")
                    upcoming["no_show_risk"] = upcoming["no_show_risk"].fillna(0)
                    upcoming = upcoming.sort_values("no_show_risk", ascending=False)
                _log_df("Analytics", "get_likely_no_shows result (alt schema)", upcoming)
                return upcoming
        _log_df("Analytics", "get_likely_no_shows result (upcoming only)", upcoming)
        return upcoming

    # Fallback 1: most recent 10 "upcoming" (on or after today)
    mask_upcoming = appointments["appt_date_only"] >= today
    if mask_upcoming.sum() > 0:
        upcoming = appointments.loc[mask_upcoming].sort_values("_dt").head(10).copy()
        upcoming = upcoming.drop(columns=["_dt", "appt_date_only"], errors="ignore")
        risk_df = get_risk_scores()
        if risk_df is not None and not risk_df.empty and "no_show_risk" in risk_df.columns and "patient_id" in risk_df.columns:
            no_show_risk = risk_df[["patient_id", "no_show_risk"]].copy()
            upcoming = upcoming.merge(no_show_risk, on="patient_id", how="left")
            upcoming["no_show_risk"] = upcoming["no_show_risk"].fillna(0)
            upcoming = upcoming.sort_values("no_show_risk", ascending=False)
        _log_empty("NoShow", "target date had 0 rows; using 10 upcoming appointments", len(upcoming))
        _log_df("Analytics", "get_likely_no_shows result (10 upcoming)", upcoming)
        return upcoming

    # Fallback 2: historical no-shows in last 30 days
    thirty_days_ago = (ref - pd.Timedelta(days=30)).date() if hasattr(ref, "date") else ref
    no_show_col = "no_show" if "no_show" in appointments.columns else None
    if no_show_col:
        mask_fallback = (
            (appointments[no_show_col].fillna(False).astype(bool))
            & (appointments["appt_date_only"] >= thirty_days_ago)
        )
        result = appointments.loc[mask_fallback].copy()
        if not result.empty:
            result["note"] = "historical no-show (last 30 days)"
            result = result.drop(columns=["_dt", "appt_date_only"], errors="ignore")
            _log_empty("NoShow", "target date had 0 rows; using historical no-shows (last 30d)", len(result))
            _log_df("Analytics", "get_likely_no_shows result (fallback 30d)", result)
            return result

    # Fallback 3: last 10 appointments in dataset (always return data when appointments exist)
    last_10 = appointments.sort_values("_dt", ascending=False).head(10).copy()
    last_10 = last_10.drop(columns=["_dt", "appt_date_only"], errors="ignore")
    _log_empty("NoShow", "target date had 0 rows; using last 10 appointments in dataset", len(last_10))
    _log_df("Analytics", "get_likely_no_shows result (last 10)", last_10)
    return last_10


MIN_TREND_DAYS = 7  # minimum rows for plotting; expand window if fewer

def get_admissions_trend(days: int = 30) -> pd.DataFrame:
    """
    Return daily admission and discharge counts for the last N days.
    Uses global data reference date so historical datasets work.
    If the filtered window has too few rows, expands the window automatically.
    Always returns a DataFrame with columns date, admissions, discharges (never None).
    """
    admissions = get_admissions()
    _log_df("Analytics", "get_admissions_trend (admissions)", admissions)
    if admissions is None or admissions.empty:
        return pd.DataFrame(columns=TREND_EMPTY_COLS)

    adate = _safe_date_col(admissions, ["admission_date", "admit_date", "start_date", "date"])
    ddate = _safe_date_col(admissions, ["discharge_date", "discharge_at", "end_date"])
    if not adate:
        return pd.DataFrame(columns=TREND_EMPTY_COLS)

    df = admissions.copy()
    df[adate] = pd.to_datetime(df[adate], errors="coerce", format="mixed")
    df = df.dropna(subset=[adate])
    if df.empty:
        return pd.DataFrame(columns=TREND_EMPTY_COLS)

    ref_ts = get_data_reference_date()
    if not isinstance(ref_ts, pd.Timestamp):
        ref_ts = pd.Timestamp(ref_ts)
    cutoff = ref_ts - pd.Timedelta(days=days)
    mask = df[adate] >= cutoff
    filtered = df.loc[mask].copy()

    # Defensive: ensure enough data for plotting (expand window if too few rows)
    min_rows = MIN_TREND_DAYS
    if len(filtered) == 0:
        _log_empty("Trend", "date window returned 0 rows; using last N rows by date", min_rows)
        filtered = df.sort_values(adate).tail(max(days, min_rows)).copy()
    else:
        n_dates = filtered[adate].dt.date.nunique()
        if n_dates < MIN_TREND_DAYS:
            expanded_days = min(days * 2, 365)
            cutoff2 = ref_ts - pd.Timedelta(days=expanded_days)
            filtered = df.loc[df[adate] >= cutoff2].copy()
            _log("Analytics", "get_admissions_trend expanded window", reason=f"<{MIN_TREND_DAYS} days", expanded_days=expanded_days, rows=len(filtered))

    _log("Analytics", "get_admissions_trend", ref_date=str(ref_ts), cutoff=str(cutoff), filtered_rows=len(filtered))
    filtered["date"] = filtered[adate].dt.date
    id_col = "admission_id" if "admission_id" in filtered.columns else filtered.columns[0]
    trend = filtered.groupby("date").agg(admissions=(id_col, "count")).reset_index()

    if ddate and ddate in df.columns:
        df[ddate] = pd.to_datetime(df[ddate], errors="coerce", format="mixed")
        df["ddate"] = df[ddate].dt.date
        discharges = df.dropna(subset=[ddate]).groupby("ddate").agg(discharges=(id_col, "count")).reset_index()
        discharges = discharges.rename(columns={"ddate": "date"})
        trend = trend.merge(discharges, on="date", how="left")
        trend["discharges"] = trend["discharges"].fillna(0).astype(int)
    else:
        trend["discharges"] = 0

    trend["date"] = pd.to_datetime(trend["date"])
    out = trend.sort_values("date")
    _log_df("Analytics", "get_admissions_trend result", out)
    return out


def get_no_show_rates() -> pd.DataFrame:
    """Public API: no-show rate by department. Same as get_department_no_show_rates()."""
    return get_department_no_show_rates()


def get_department_no_show_rates() -> pd.DataFrame:
    """
    Return no-show rate by department. Expects appointments table with:
    - department (or column containing 'department'/'dept')
    - no_show (bool) or status/outcome column indicating no-show.
    Raises on fetch errors.
    """
    appointments = get_appointments()
    _log_df("Analytics", "get_no_show_rates (appointments)", appointments)
    if appointments is None or appointments.empty:
        _log_empty("NoShow", "appointments table", 0)
        return pd.DataFrame(columns=DEPT_NO_SHOW_EMPTY_COLS)

    dept_col = next((c for c in appointments.columns if "department" in c.lower() or "dept" in c.lower()), None)
    status_col = next((c for c in appointments.columns if "status" in c.lower() or "outcome" in c.lower()), None)
    no_show_col = "no_show" if "no_show" in appointments.columns else None

    if not dept_col:
        dept_col = "department"
        appointments = appointments.copy()
        appointments[dept_col] = "Unknown"

    appointments = appointments.copy()
    if no_show_col:
        appointments["_no_show"] = appointments[no_show_col].fillna(False).astype(bool)
    elif status_col:
        appointments["_no_show"] = appointments[status_col].astype(str).str.lower().str.contains(
            "no-show|noshow|cancel|no_show", na=False, regex=True
        )
    else:
        agg = appointments.groupby(dept_col).size().reset_index(name="total_appointments")
        agg["no_shows"] = 0
        agg["no_show_rate"] = 0.0
        out = agg.rename(columns={dept_col: "department"}) if dept_col != "department" else agg
        _log_df("Analytics", "get_no_show_rates result (counts only)", out)
        return out

    agg = appointments.groupby(dept_col).agg(total=("_no_show", "count"), no_shows=("_no_show", "sum")).reset_index()
    agg["no_show_rate"] = (agg["no_shows"] / agg["total"].replace(0, 1)).round(4)
    agg = agg.sort_values("no_show_rate", ascending=False)
    out = agg.rename(columns={"total": "total_appointments", "no_shows": "no_shows"})
    if dept_col != "department":
        out = out.rename(columns={dept_col: "department"})
    _log_df("Analytics", "get_no_show_rates result", out)
    return out


def get_icu_patients(limit: int = 200) -> pd.DataFrame:
    """
    Return patients currently in ICU (from icu_beds where patient_id is present).
    Merges with patients and risk_scores for display.
    """
    beds = get_icu_beds()
    patients = get_patients()
    risk_scores = get_risk_scores()
    _log_df("Analytics", "get_icu_patients (icu_beds)", beds)
    if beds is None or beds.empty:
        return pd.DataFrame()
    pid_col = "patient_id" if "patient_id" in beds.columns else None
    if not pid_col:
        return pd.DataFrame()
    occ_col = "occupied" if "occupied" in beds.columns else "status"
    if occ_col in beds.columns:
        if beds[occ_col].dtype == bool:
            occupied = beds[beds[occ_col]].copy()
        else:
            occupied = beds[beds[occ_col].astype(str).str.lower().isin(("true", "1", "occupied", "yes"))].copy()
    else:
        occupied = beds[beds[pid_col].notna()].copy()
    if occupied.empty:
        occupied = beds[beds[pid_col].notna()].copy()
    if occupied.empty:
        return pd.DataFrame()
    pids = occupied[pid_col].astype(str).unique().tolist()[:limit]
    if not pids:
        return pd.DataFrame()
    out = patients[patients["patient_id"].astype(str).isin(pids)].copy() if not patients.empty and "patient_id" in patients.columns else pd.DataFrame(columns=["patient_id"])
    if out.empty:
        out = pd.DataFrame([{"patient_id": pid} for pid in pids])
    if not risk_scores.empty and "patient_id" in risk_scores.columns:
        rs = risk_scores[risk_scores["patient_id"].astype(str).isin(pids)].drop_duplicates(subset=["patient_id"], keep="first")
        out = out.merge(rs, on="patient_id", how="left", suffixes=("", "_rs"))
        out = out[[c for c in out.columns if not c.endswith("_rs")]]
    _log_df("Analytics", "get_icu_patients result", out)
    return out


def get_patient_list_for_dashboard(limit: int = 500) -> pd.DataFrame:
    """
    Return patient list for drill-down view: patients merged with risk_scores.
    Columns: patient_id, age, gender, diagnosis, heart_rate, blood_pressure, oxygen,
    icu_status, readmission_risk, no_show_risk (when available).
    """
    patients = get_patients()
    risk_scores = get_risk_scores()
    beds = get_icu_beds()
    _log_df("Analytics", "get_patient_list_for_dashboard (patients)", patients)
    if patients is None or patients.empty:
        return pd.DataFrame()
    out = patients.head(limit).copy()
    if not risk_scores.empty and "patient_id" in risk_scores.columns:
        rs = risk_scores.drop_duplicates(subset=["patient_id"], keep="first")
        merge_cols = ["patient_id"] + [c for c in rs.columns if c != "patient_id"]
        out = out.merge(rs[merge_cols], on="patient_id", how="left", suffixes=("", "_rs"))
        out = out[[c for c in out.columns if not c.endswith("_rs")]]
    if beds is not None and not beds.empty and "patient_id" in beds.columns:
        occ_col = "occupied" if "occupied" in beds.columns else "status"
        icu_pids = set()
        if occ_col in beds.columns:
            occ_beds = beds[beds[occ_col].fillna(False).astype(bool)] if beds[occ_col].dtype == bool else beds[beds[occ_col].astype(str).str.lower().isin(("true", "1", "occupied", "yes"))]
            icu_pids = set(occ_beds["patient_id"].dropna().astype(str))
        else:
            icu_pids = set(beds["patient_id"].dropna().astype(str))
        out["icu_status"] = out["patient_id"].astype(str).map(lambda x: "Yes" if x in icu_pids else "No")
    else:
        out["icu_status"] = "Unknown"
    _log_df("Analytics", "get_patient_list_for_dashboard result", out)
    return out


def get_patient_id_list(max_ids: int = 500) -> list[str]:
    """
    Return sorted list of patient IDs for selectors (e.g. dashboard dropdown).
    Uses data repository only; no other processing.
    """
    patients = get_patients()
    _log_df("Analytics", "get_patient_id_list (patients)", patients)
    if patients is None or patients.empty or "patient_id" not in patients.columns:
        _log("Analytics", "get_patient_id_list result", count=0, ids=[])
        return []
    ids = patients["patient_id"].astype(str).unique().tolist()
    out = sorted(ids)[:max_ids]
    _log("Analytics", "get_patient_id_list result", count=len(out), sample=out[:5] if out else [])
    return out


def get_patient_history(patient_id: str | int) -> dict[str, Any]:
    """
    Return consolidated patient history: demographics, vitals, admissions, risk scores.
    Formatted for the Patient Digital Twin Viewer.
    Uses filtered vitals fetch (avoids loading 120k+ rows).
    """
    _pt = get_patients()
    patients = _pt if _pt is not None else pd.DataFrame()
    _adm = get_admissions()
    admissions = _adm if _adm is not None else pd.DataFrame()
    _rs = get_risk_scores()
    risk_scores = _rs if _rs is not None else pd.DataFrame()
    _log_df("Analytics", "get_patient_history (patients)", patients)
    _log_df("Analytics", "get_patient_history (admissions)", admissions)
    _log_df("Analytics", "get_patient_history (risk_scores)", risk_scores)

    pid = str(patient_id) if patient_id is not None else None
    if not pid:
        return {"demographics": {}, "vitals": pd.DataFrame(), "admissions": pd.DataFrame(), "risk_scores": pd.DataFrame()}

    # Normalize patient_id in DataFrames for matching
    def _norm_id(df: pd.DataFrame, col: str = "patient_id") -> pd.DataFrame:
        if col not in df.columns:
            return df
        df = df.copy()
        df[col] = df[col].astype(str)
        return df

    patients = _norm_id(patients)
    admissions = _norm_id(admissions)
    risk_scores = _norm_id(risk_scores)

    demographics = {}
    if not patients.empty:
        row = patients[patients["patient_id"] == pid]
        if not row.empty:
            demographics = row.iloc[0].to_dict()

    adm = admissions[admissions["patient_id"] == pid] if not admissions.empty else pd.DataFrame()
    vit = get_vitals_for_patient(pid)  # filtered fetch - only this patient's vitals
    if not vit.empty and "_date" not in vit.columns:
        date_cand = [c for c in vit.columns if "date" in c.lower() or "time" in c.lower() or "recorded" in c.lower()]
        if date_cand:
            vit = vit.sort_values(date_cand[0], ascending=False).head(50)

    risk = risk_scores[risk_scores["patient_id"] == pid] if not risk_scores.empty else pd.DataFrame()

    _log(
        "Analytics",
        "get_patient_history result",
        patient_id=pid,
        demographics_keys=len(demographics),
        vitals_rows=len(vit),
        admissions_rows=len(adm),
        risk_scores_rows=len(risk),
    )
    return {
        "demographics": demographics,
        "vitals": vit,
        "admissions": adm,
        "risk_scores": risk,
    }


# ---- Standalone run for debugging (python -m hospital_analytics or python hospital_analytics.py) ----
if __name__ == "__main__":
    import os
    os.environ.setdefault("DEBUG", "1")
    from dotenv import load_dotenv
    from pathlib import Path
    for p in [Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"]:
        if p.exists():
            load_dotenv(p)
            break

    print("--- Analytics engine standalone run (DEBUG=1) ---")
    print("compute_icu_occupancy():", compute_icu_occupancy())
    print("get_total_patients():", get_total_patients())
    print("get_high_risk_patients(limit=5) shape:", get_high_risk_patients(limit=5).shape)
    print("get_no_show_rates() shape:", get_no_show_rates().shape)
    print("get_likely_no_shows(days_ahead=1) shape:", get_likely_no_shows(days_ahead=1).shape)
    trend = get_admissions_trend(days=7)
    print("get_admissions_trend(days=7) shape:", trend.shape)
    ids = get_patient_id_list(max_ids=10)
    print("get_patient_id_list(max_ids=10) length:", len(ids), "sample:", ids[:3])
    if ids:
        hist = get_patient_history(ids[0])
        print("get_patient_history(sample_id) keys:", list(hist.keys()), "demographics:", bool(hist["demographics"]))
    print("--- Done ---")
