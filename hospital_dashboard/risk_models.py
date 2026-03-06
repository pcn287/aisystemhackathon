"""
Layer 3 — Prediction Engine Layer

This module calculates risk indicators (0–1 scores) based on patient and
appointment features using heuristic rules. Used for readmission, ICU, and no-show risk.

Hospital assumption: patients with predicted 30-day readmission risk ≥ 0.6 are flagged.
Chronic conditions considered: hypertension, diabetes, COPD, heart failure.
"""

from typing import Any


def _get_float(d: dict, key: str, default: float = 0.0) -> float:
    """Safely get a numeric value from a dict (e.g. patient or row)."""
    if not isinstance(d, dict):
        return default
    v = d.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _get_str(d: dict, key: str, default: str = "") -> str:
    """Safely get a string value from a dict."""
    if not isinstance(d, dict):
        return default
    v = d.get(key)
    if v is None:
        return default
    return str(v).strip().lower()


def _get_bool(d: dict, key: str, default: bool = False) -> bool:
    """Safely get a boolean from a dict."""
    if not isinstance(d, dict):
        return default
    v = d.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes", "y")


def calculate_readmission_risk(patient: dict[str, Any]) -> float:
    """
    Calculate readmission risk (0–1) using heuristic rules.
    - Age above 65 increases readmission probability.
    - Additional factors (e.g. prior admissions, conditions) can be incorporated
      if present in the patient record.
    """
    score = 0.0
    age = _get_float(patient, "age", -1)
    if age >= 65:
        score += 0.25
    elif age >= 50:
        score += 0.1

    # Comorbidities that increase readmission risk (hypertension, diabetes, COPD, heart failure per hospital assumptions)
    conditions = _get_str(patient, "conditions", "") + _get_str(patient, "diagnosis", "") + _get_str(patient, "comorbidities", "")
    if "copd" in conditions or "chronic obstructive" in conditions:
        score += 0.2
    if "heart failure" in conditions or "chf" in conditions or "cardiac" in conditions:
        score += 0.2
    if "hypertension" in conditions or "htn" in conditions:
        score += 0.08
    if "diabetes" in conditions:
        score += 0.1
    if "renal" in conditions or "kidney" in conditions:
        score += 0.1

    # Prior admissions count if available
    prior = _get_float(patient, "prior_admissions", 0)
    if prior >= 2:
        score += 0.2
    elif prior >= 1:
        score += 0.1

    return min(1.0, round(score, 4))


def calculate_icu_risk(patient: dict[str, Any]) -> float:
    """
    Calculate ICU admission risk (0–1) using heuristic rules.
    - COPD or heart failure increases ICU probability.
    - Age and severity indicators can increase score.
    """
    score = 0.0
    conditions = _get_str(patient, "conditions", "") + _get_str(patient, "diagnosis", "") + _get_str(patient, "comorbidities", "")

    if "copd" in conditions or "chronic obstructive" in conditions:
        score += 0.3
    if "heart failure" in conditions or "chf" in conditions or "cardiac" in conditions:
        score += 0.25
    if "respiratory" in conditions or "pneumonia" in conditions:
        score += 0.2
    if "sepsis" in conditions or "septic" in conditions:
        score += 0.35
    if "stroke" in conditions or "neuro" in conditions:
        score += 0.15

    age = _get_float(patient, "age", -1)
    if age >= 70:
        score += 0.1
    elif age >= 65:
        score += 0.05

    return min(1.0, round(score, 4))


def calculate_no_show_risk(appointment: dict[str, Any]) -> float:
    """
    Calculate no-show risk (0–1) for an appointment using heuristic rules.
    - Longer travel distance increases no-show probability.
    - Previous no-shows, appointment type, and timing can be incorporated.
    """
    score = 0.0
    distance = _get_float(appointment, "travel_distance", -1)
    if distance > 50:
        score += 0.35
    elif distance > 25:
        score += 0.2
    elif distance > 10:
        score += 0.1

    # Prior no-shows if available
    prior_noshow = _get_float(appointment, "prior_no_shows", 0)
    if prior_noshow >= 2:
        score += 0.3
    elif prior_noshow >= 1:
        score += 0.15

    # Appointment type: follow-up vs new
    apt_type = _get_str(appointment, "appointment_type", "") + _get_str(appointment, "type", "")
    if "follow" in apt_type or "followup" in apt_type:
        score += 0.05

    return min(1.0, round(score, 4))
