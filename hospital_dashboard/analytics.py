"""
Decision support — root cause analysis and operational strain score.

analyze_readmission_drivers(df): top conditions, departments, discharge types.
hospital_strain_score(): 0–100 score with color band (green / yellow / red).
"""

from typing import Any

import pandas as pd


def analyze_readmission_drivers(df: pd.DataFrame) -> dict[str, Any]:
    """
    Root cause analysis for readmission risk from high-risk patient DataFrame.

    Expects df with columns such as: patient_id, readmission_risk, diagnosis/diagnosis_code,
    department, discharge_type (or similar). Uses whatever column names exist.

    Returns:
        {
          "top_conditions": [{"name": "COPD", "count": 84}, ...],
          "departments": [{"name": "Cardiology", "count": 45}, ...],
          "discharge_types": [{"name": "Home", "count": 120}, ...]
        }
    """
    out: dict[str, Any] = {
        "top_conditions": [],
        "departments": [],
        "discharge_types": [],
    }
    if df is None or df.empty:
        return out

    # Top diagnoses/conditions
    diag_col = None
    for c in df.columns:
        if "diagnos" in c.lower() or "condition" in c.lower() or "primary" in c.lower():
            diag_col = c
            break
    if diag_col:
        counts = df[diag_col].fillna("Unknown").astype(str).str.strip()
        counts = counts[counts != ""].replace("", "Unknown")
        top = counts.value_counts().head(15)
        out["top_conditions"] = [{"name": str(k), "count": int(v)} for k, v in top.items()]

    # Department distribution
    dept_col = None
    for c in df.columns:
        if "department" in c.lower() or "dept" in c.lower():
            dept_col = c
            break
    if dept_col:
        counts = df[dept_col].fillna("Unknown").astype(str).str.strip().str.capitalize()
        counts = counts.replace("", "Unknown")
        top = counts.value_counts().head(10)
        out["departments"] = [{"name": str(k), "count": int(v)} for k, v in top.items()]

    # Discharge type distribution
    disc_col = None
    for c in df.columns:
        if "discharge_type" in c.lower() or "disposition" in c.lower() or "discharge_disposition" in c.lower():
            disc_col = c
            break
    if disc_col:
        counts = df[disc_col].fillna("Unknown").astype(str).str.strip().str.capitalize()
        counts = counts.replace("", "Unknown")
        top = counts.value_counts().head(10)
        out["discharge_types"] = [{"name": str(k), "count": int(v)} for k, v in top.items()]

    return out


def hospital_strain_score(
    icu_occupancy_pct: float,
    readmission_rate: float,
    no_show_rate: float,
) -> tuple[float, str]:
    """
    Operational risk (Hospital Strain) score 0–100 and status label.

    Formula: 0.5 * ICU occupancy + 0.3 * readmission_rate + 0.2 * no_show_rate,
    with rates in 0–1 scale (ICU occupancy as 0–1, e.g. 90% -> 0.9).

    Returns:
        (score_0_100, status)
        status: "normal" (0–30), "elevated" (30–60), "critical" (60+)
    """
    if icu_occupancy_pct > 1:
        icu_occupancy_pct = icu_occupancy_pct / 100.0
    score = (
        0.5 * min(1.0, max(0, icu_occupancy_pct))
        + 0.3 * min(1.0, max(0, readmission_rate))
        + 0.2 * min(1.0, max(0, no_show_rate))
    ) * 100
    score = round(min(100.0, max(0.0, score)), 1)
    if score <= 30:
        status = "normal"
    elif score <= 60:
        status = "elevated"
    else:
        status = "critical"
    return score, status
