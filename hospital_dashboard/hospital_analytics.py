"""
Layer 2 — Analytics Query Layer

This module computes hospital metrics using data from the Supabase data access layer.
All functions return results formatted for dashboard visualization.

Hospital profile (assumptions):
- ~5000 patients, 250–300 beds, 50 ICU beds. Departments: Cardiology, Pulmonology,
  Oncology, Orthopedics, General Medicine.
- High readmission risk: 30-day readmission risk ≥ READMISSION_RISK_THRESHOLD (0.6).
- ICU high operational risk: occupancy above ICU_HIGH_RISK_OCCUPANCY (90%).
"""

from typing import Any, Optional

import pandas as pd

# Operational thresholds (hospital assumptions)
READMISSION_RISK_THRESHOLD = 0.6   # Patients above this are flagged in the system
ICU_HIGH_RISK_OCCUPANCY = 0.9     # ICU occupancy ≥ 90% = high operational risk

from database_connection import (
    get_patients,
    get_admissions,
    get_vitals,
    get_vitals_for_patient,
    get_appointments,
    get_icu_beds,
    get_risk_scores,
)


def _safe_date_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return first existing column name from candidates, or None."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def get_total_patients() -> int:
    """
    Return total number of distinct patients in the system.
    """
    patients = get_patients()
    if "patient_id" in patients.columns:
        return int(patients["patient_id"].nunique())
    return len(patients)


def get_icu_occupancy() -> dict[str, Any]:
    """
    Return ICU occupancy metrics: total beds, occupied beds, occupancy rate.
    Assumes icu_beds has columns like bed_id, occupied (or status), and optionally unit.
    """
    beds = get_icu_beds()
    if beds.empty:
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
    return {
        "total": total,
        "occupied": occupied,
        "rate": round(rate, 4),
        "high_operational_risk": rate >= ICU_HIGH_RISK_OCCUPANCY,  # ≥90% per hospital assumption
    }


def get_high_readmission_patients(limit: int = 20) -> pd.DataFrame:
    """
    Return patients flagged with high 30-day readmission risk (≥ READMISSION_RISK_THRESHOLD),
    sorted by risk, top N. Uses risk_scores when available, else derives from admissions.
    """
    risk_df = get_risk_scores()
    patients = get_patients()
    admissions = get_admissions()

    # Schema with readmission_risk column (our Supabase schema)
    if not risk_df.empty and "readmission_risk" in risk_df.columns and "patient_id" in risk_df.columns:
        out = risk_df[risk_df["readmission_risk"] >= READMISSION_RISK_THRESHOLD].copy()
        out = out.sort_values("readmission_risk", ascending=False).head(limit)
        if not patients.empty and "patient_id" in patients.columns:
            out = out.merge(patients, on="patient_id", how="left")
        return out

    # Alternative schema: score_type + value
    if not risk_df.empty and "score_type" in risk_df.columns and "patient_id" in risk_df.columns:
        readmission = risk_df[risk_df["score_type"].astype(str).str.lower().str.contains("readmission", na=False)]
        if not readmission.empty:
            value_col = "value" if "value" in readmission.columns else "score"
            if value_col not in readmission.columns:
                value_col = readmission.select_dtypes(include="number").columns[0] if len(readmission.select_dtypes(include="number").columns) else None
            if value_col:
                out = readmission.groupby("patient_id")[value_col].max().reset_index()
                out = out.rename(columns={value_col: "readmission_risk"})
                out = out[out["readmission_risk"] >= READMISSION_RISK_THRESHOLD]
                out = out.sort_values("readmission_risk", ascending=False).head(limit)
                if not patients.empty and "patient_id" in patients.columns:
                    out = out.merge(patients, on="patient_id", how="left")
                return out

    # Fallback: use admission count as proxy; normalize to 0–1 and filter by threshold
    if not admissions.empty and "patient_id" in admissions.columns:
        counts = admissions.groupby("patient_id").size().reset_index(name="admission_count")
        max_count = counts["admission_count"].max()
        counts["readmission_risk"] = (counts["admission_count"] / max_count).clip(0, 1) if max_count else 0
        counts = counts[counts["readmission_risk"] >= READMISSION_RISK_THRESHOLD]
        counts = counts.sort_values("readmission_risk", ascending=False).head(limit)
        if not patients.empty and "patient_id" in patients.columns:
            counts = counts.merge(patients, on="patient_id", how="left")
        return counts

    return pd.DataFrame()


def get_likely_no_shows(days_ahead: int = 1) -> pd.DataFrame:
    """
    Return appointments in the next N days that are likely no-shows.
    Uses risk_scores when available (no_show risk), otherwise returns upcoming appointments.
    """
    appointments = get_appointments()
    if appointments.empty:
        return pd.DataFrame()

    date_col = _safe_date_col(appointments, ["appointment_date", "scheduled_date", "date", "appointment_at"])
    if not date_col:
        return pd.DataFrame()

    appointments = appointments.copy()
    appointments[date_col] = pd.to_datetime(appointments[date_col], errors="coerce")
    appointments = appointments.dropna(subset=[date_col])

    today = pd.Timestamp.now().normalize()
    end = today + pd.Timedelta(days=days_ahead)
    upcoming = appointments[(appointments[date_col].dt.date >= today.date()) & (appointments[date_col].dt.date <= end.date())]

    risk_df = get_risk_scores()
    # Schema with no_show_risk column (our Supabase schema)
    if not risk_df.empty and "no_show_risk" in risk_df.columns and "patient_id" in risk_df.columns:
        no_show_risk = risk_df[["patient_id", "no_show_risk"]].copy()
        upcoming = upcoming.merge(no_show_risk, on="patient_id", how="left")
        upcoming["no_show_risk"] = upcoming["no_show_risk"].fillna(0)
        upcoming = upcoming.sort_values("no_show_risk", ascending=False)
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
            return upcoming

    return upcoming


def get_admissions_trend(days: int = 30) -> pd.DataFrame:
    """
    Return daily admission and discharge counts for the last N days.
    DataFrame columns: date, admissions, discharges (or similar).
    """
    admissions = get_admissions()
    if admissions.empty:
        return pd.DataFrame()

    adate = _safe_date_col(admissions, ["admission_date", "admit_date", "start_date", "date"])
    ddate = _safe_date_col(admissions, ["discharge_date", "discharge_at", "end_date"])
    if not adate:
        return pd.DataFrame()

    admissions = admissions.copy()
    admissions[adate] = pd.to_datetime(admissions[adate], errors="coerce")
    admissions = admissions.dropna(subset=[adate])
    if ddate:
        admissions[ddate] = pd.to_datetime(admissions[ddate], errors="coerce")

    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)
    admissions = admissions[admissions[adate] >= cutoff]

    admissions["_date"] = admissions[adate].dt.date
    daily_adm = admissions.groupby("_date").size().reset_index(name="admissions")

    if ddate:
        admissions["_ddate"] = admissions[ddate].dt.date
        daily_dis = admissions.dropna(subset=[ddate]).groupby("_ddate").size().reset_index(name="discharges")
        daily_adm = daily_adm.merge(daily_dis, left_on="_date", right_on="_ddate", how="left")
        daily_adm["discharges"] = daily_adm["discharges"].fillna(0).astype(int)
        daily_adm = daily_adm.drop(columns=["_ddate"], errors="ignore")

    daily_adm = daily_adm.rename(columns={"_date": "date"})
    daily_adm["date"] = pd.to_datetime(daily_adm["date"])
    return daily_adm.sort_values("date")


def get_department_no_show_rates() -> pd.DataFrame:
    """
    Return no-show rate by department (or similar grouping).
    Assumes appointments have department (or department_id) and status (no-show, completed, etc.).
    """
    appointments = get_appointments()
    if appointments.empty:
        return pd.DataFrame()

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
        appointments["_no_show"] = appointments[status_col].astype(str).str.lower().str.contains("no.show|noshow|cancel|no-show", na=False, regex=True)
    else:
        return appointments.groupby(dept_col).size().reset_index(name="total_appointments")
    agg = appointments.groupby(dept_col).agg(total=("_no_show", "count"), no_shows=("_no_show", "sum")).reset_index()
    agg["no_show_rate"] = (agg["no_shows"] / agg["total"]).round(4)
    agg = agg.sort_values("no_show_rate", ascending=False)
    return agg.rename(columns={"total": "total_appointments", "no_shows": "no_shows"})


def get_patient_history(patient_id: str | int) -> dict[str, Any]:
    """
    Return consolidated patient history: demographics, vitals, admissions, risk scores.
    Formatted for the Patient Digital Twin Viewer.
    Uses filtered vitals fetch (avoids loading 120k+ rows).
    """
    patients = get_patients()
    admissions = get_admissions()
    risk_scores = get_risk_scores()

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

    return {
        "demographics": demographics,
        "vitals": vit,
        "admissions": adm,
        "risk_scores": risk,
    }


def predict_icu_capacity_reach_90() -> dict[str, Any]:
    """
    Q2: Under today's admission forecast, when will ICU capacity reach 90%?
    Uses historical ICU-required admissions to estimate days until 90%.
    """
    icu = get_icu_occupancy()
    admissions = get_admissions()
    trend = get_admissions_trend(days=30)

    total = icu.get("total", 50)
    occupied = icu.get("occupied", 0)
    target = min(45, int(total * 0.9))  # 90% of 50 = 45
    beds_until_90 = target - occupied

    result = {
        "current_occupied": occupied,
        "total_beds": total,
        "target_90pct": target,
        "beds_until_90": beds_until_90,
        "already_at_risk": occupied >= target,
        "estimated_days": None,
        "forecast_note": "",
    }

    if beds_until_90 <= 0:
        result["forecast_note"] = "ICU is already at or above 90% capacity. Immediate action recommended."
        return result

    adate = _safe_date_col(admissions, ["admission_date", "admit_date", "start_date", "date"])
    icu_col = "icu_required" if "icu_required" in admissions.columns else None
    if adate and icu_col and not admissions.empty:
        adm = admissions.copy()
        adm[adate] = pd.to_datetime(adm[adate], errors="coerce")
        adm = adm.dropna(subset=[adate])
        cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=30)
        recent = adm[adm[adate] >= cutoff]
        if not recent.empty:
            icu_adm = recent[recent[icu_col] == True]
            days_span = max(1, (recent[adate].max() - recent[adate].min()).days)
            avg_icu = len(icu_adm) / days_span
            if avg_icu > 0:
                result["estimated_days"] = round(beds_until_90 / avg_icu, 1)
                result["forecast_note"] = f"At current rate (~{avg_icu:.1f} ICU admissions/day), 90% in ~{result['estimated_days']:.0f} days."

    if result["estimated_days"] is None and not trend.empty and "admissions" in trend.columns:
        avg_adm = trend["admissions"].mean()
        proxy_icu = max(0.1, avg_adm * 0.15)
        result["estimated_days"] = round(beds_until_90 / proxy_icu, 1)
        result["forecast_note"] = f"Based on admission trend (proxy ~{proxy_icu:.1f} ICU/day), 90% in ~{result['estimated_days']:.0f} days."

    if result["forecast_note"] == "":
        result["forecast_note"] = "Insufficient data for forecast. Monitor admissions closely."

    return result


def get_similar_patients(patient_id: str | int, n: int = 5) -> dict[str, Any]:
    """
    Q3: Find historical cases with similar risk factors for comparison.
    """
    pid = str(patient_id)
    risk_df = get_risk_scores()
    patients = get_patients()
    admissions = get_admissions()

    if risk_df.empty or "patient_id" not in risk_df.columns:
        return {"patient_id": pid, "similar": [], "patient_profile": {}, "note": "No risk scores."}

    score_cols = [c for c in ["readmission_risk", "icu_risk", "no_show_risk"] if c in risk_df.columns]
    if not score_cols:
        return {"patient_id": pid, "similar": [], "patient_profile": {}, "note": "Risk columns not found."}

    patient_row = risk_df[risk_df["patient_id"].astype(str) == pid]
    if patient_row.empty:
        return {"patient_id": pid, "similar": [], "patient_profile": {}, "note": "Patient not found."}

    patient_scores = patient_row[score_cols].iloc[0].fillna(0)
    others = risk_df[risk_df["patient_id"].astype(str) != pid].copy()
    others[score_cols] = others[score_cols].fillna(0)
    diff = others[score_cols] - patient_scores.values
    others["_dist"] = (diff ** 2).sum(axis=1) ** 0.5
    top = others.nsmallest(n, "_dist")

    similar_list = []
    for _, row in top.iterrows():
        spid = str(row["patient_id"])
        rec = {"patient_id": spid, "readmission_risk": row.get("readmission_risk"), "icu_risk": row.get("icu_risk"), "no_show_risk": row.get("no_show_risk")}
        if not patients.empty:
            prow = patients[patients["patient_id"].astype(str) == spid]
            if not prow.empty:
                rec["age"] = prow.iloc[0].get("age")
                rec["primary_diagnosis"] = prow.iloc[0].get("primary_diagnosis")
        if not admissions.empty:
            rec["admission_count"] = len(admissions[admissions["patient_id"].astype(str) == spid])
        similar_list.append(rec)

    profile = patient_row.iloc[0].to_dict()
    if not patients.empty:
        prow = patients[patients["patient_id"].astype(str) == pid]
        if not prow.empty:
            profile.update(prow.iloc[0].to_dict())

    return {"patient_id": pid, "patient_profile": profile, "similar": similar_list}


def get_patient_risk_merged() -> pd.DataFrame:
    """
    Return merged patients + risk_scores for exploratory analysis and regression plots.
    """
    patients = get_patients()
    risk_scores = get_risk_scores()
    if patients.empty or risk_scores.empty:
        return pd.DataFrame()
    patients = patients.copy()
    patients["patient_id"] = patients["patient_id"].astype(str)
    risk_scores = risk_scores.copy()
    risk_scores["patient_id"] = risk_scores["patient_id"].astype(str)
    return patients.merge(risk_scores, on="patient_id", how="inner")


def get_descriptive_stats(df: pd.DataFrame, numeric_cols: list[str] | None = None) -> dict[str, dict]:
    """Return descriptive stats (count, mean, sd, min, max) for numeric columns."""
    if df.empty:
        return {}
    if numeric_cols is None:
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    out = {}
    for col in numeric_cols:
        s = df[col].dropna()
        out[col] = {"count": len(s), "mean": round(s.mean(), 4), "sd": round(s.std(), 4) if len(s) > 1 else 0, "min": s.min(), "max": s.max()}
    return out


def get_vitals_summary(sample_size: int = 3000) -> dict[str, Any]:
    """
    Return descriptive stats for post-discharge vitals (heart_rate, systolic_bp, oxygen_saturation, etc.).
    Uses a sample for performance. Includes sample DataFrame for charting.
    """
    vitals = get_vitals()
    if vitals.empty:
        return {"n_records": 0, "n_patients": 0, "stats": {}, "sample": pd.DataFrame()}
    vitals = vitals.head(sample_size)
    cols = [c for c in ["heart_rate", "systolic_bp", "respiratory_rate", "oxygen_saturation", "temperature"] if c in vitals.columns]
    stats = get_descriptive_stats(vitals, cols)
    n_patients = vitals["patient_id"].nunique() if "patient_id" in vitals.columns else 0
    return {"n_records": len(vitals), "n_patients": n_patients, "stats": stats, "sample": vitals}
