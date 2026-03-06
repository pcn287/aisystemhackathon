"""
Layer 4 — LLM Insight Engine

This module integrates with an LLM via an OpenAI-compatible API to provide
decision support. The AI does NOT generate raw predictions; it INTERPRETS
risk scores, SUMMARIZES trends, and SUGGESTS operational actions based only
on supplied structured data from the analytics layer (no fabricated numbers).
"""

import json
import os
from typing import Any, Optional

from hospital_analytics import (
    get_total_patients,
    get_icu_occupancy,
    get_high_readmission_patients,
    get_likely_no_shows,
    get_admissions_trend,
    get_department_no_show_rates,
    get_patient_history,
)


def _get_client():
    """Lazy import and create OpenAI-compatible client from env."""
    try:
        from openai import OpenAI
    except ImportError:
        return None
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")  # Optional: for non-OpenAI endpoints
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url=base_url if base_url else None)


def _call_llm(system_prompt: str, user_content: str, max_tokens: int = 1024) -> str:
    """
    Call LLM with system and user messages. Returns model response text or fallback.
    """
    client = _get_client()
    if client is None:
        return (
            "LLM not available. Set OPENAI_API_KEY (or LLM_API_KEY) and optionally OPENAI_BASE_URL "
            "for an OpenAI-compatible API."
        )
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=max_tokens,
        )
        if r.choices and len(r.choices) > 0:
            return (r.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Error calling LLM: {e}"
    return "No response from model."


# Hospital profile passed to LLM for context (decision-support assumptions)
_HOSPITAL_PROFILE = {
    "icu_total_beds": 50,
    "icu_high_risk_occupancy_pct": 90,
    "readmission_risk_flag_threshold": 0.6,
    "baseline_readmission_rate": "10–20%",
    "typical_no_show_rate": "10–25%",
    "departments": ["Cardiology", "Pulmonology", "Oncology", "Orthopedics", "General Medicine"],
    "vital_signs_monitored": ["heart_rate", "blood_pressure", "respiratory_rate", "oxygen_saturation", "body_temperature"],
}

_SYSTEM_PROMPT = """You are a hospital decision-support AI. Your role is to:
- INTERPRET risk scores and metrics (e.g. readmission risk ≥ 0.6 is flagged; ICU occupancy ≥ 90% is high operational risk).
- SUMMARIZE trends and patterns from the data provided.
- SUGGEST operational actions (e.g. resource allocation, care prioritization).

You do NOT generate raw predictions or invent numbers. Use ONLY the data in the user message. If data is missing or insufficient, say so. Keep language clear and suitable for clinicians and administrators."""


def generate_operational_summary() -> str:
    """
    Generate a short operational summary using current hospital metrics from Supabase.
    """
    total = get_total_patients()
    icu = get_icu_occupancy()
    high_readmission = get_high_readmission_patients(limit=5)
    no_shows = get_likely_no_shows(days_ahead=1)
    trend = get_admissions_trend(days=7)
    dept_no_show = get_department_no_show_rates()

    data = {
        "hospital_profile": _HOSPITAL_PROFILE,
        "total_patients": total,
        "icu_occupancy": icu,
        "high_readmission_patient_count": len(high_readmission),
        "likely_no_shows_tomorrow_count": len(no_shows),
        "admissions_trend_last_7_days": trend.to_dict(orient="records") if not trend.empty else [],
        "department_no_show_rates": dept_no_show.head(10).to_dict(orient="records") if not dept_no_show.empty else [],
    }
    user_content = "Using ONLY the data below, write a brief operational summary (2–4 sentences). Reference hospital profile thresholds where relevant.\n\n" + json.dumps(data, default=str)
    return _call_llm(_SYSTEM_PROMPT, user_content)


def explain_patient_risk(patient_id: str | int) -> str:
    """
    Explain risk for a specific patient using their history and risk data from Supabase.
    """
    history = get_patient_history(patient_id)
    data = {
        "hospital_profile": _HOSPITAL_PROFILE,
        "demographics": history["demographics"],
        "admissions_count": len(history["admissions"]),
        "vitals_records_count": len(history["vitals"]),
        "risk_scores": history["risk_scores"].to_dict(orient="records") if not history["risk_scores"].empty else [],
    }
    user_content = (
        f"Using ONLY the data below for patient_id={patient_id}, interpret this patient's risk profile "
        "(readmission ≥ 0.6 is flagged; mention vitals only if present). Do not invent numbers.\n\n" + json.dumps(data, default=str)
    )
    return _call_llm(_SYSTEM_PROMPT, user_content)


def predict_capacity_alerts() -> str:
    """
    Generate capacity-related alerts (e.g. ICU) using current occupancy and trends.
    """
    icu = get_icu_occupancy()
    trend = get_admissions_trend(days=14)
    data = {
        "hospital_profile": _HOSPITAL_PROFILE,
        "icu_occupancy": icu,
        "admissions_trend": trend.to_dict(orient="records") if not trend.empty else [],
    }
    user_content = (
        "Using ONLY the data below, summarize ICU capacity. ICU occupancy ≥ 90% is high operational risk (50 beds). "
        "Suggest actions if needed. Do not invent numbers.\n\n" + json.dumps(data, default=str)
    )
    return _call_llm(_SYSTEM_PROMPT, user_content)


def answer_user_question(query: str) -> str:
    """
    Answer a natural language question using live data from analytics functions.
    The LLM receives structured data and must reason only from it.
    """
    total = get_total_patients()
    icu = get_icu_occupancy()
    high_readmission = get_high_readmission_patients(limit=20)
    no_shows = get_likely_no_shows(days_ahead=7)
    trend = get_admissions_trend(days=30)
    dept_no_show = get_department_no_show_rates()

    data = {
        "hospital_profile": _HOSPITAL_PROFILE,
        "total_patients": total,
        "icu_occupancy": icu,
        "high_readmission_patients": high_readmission.head(20).to_dict(orient="records") if not high_readmission.empty else [],
        "likely_no_shows_next_7_days_count": len(no_shows),
        "admissions_trend": trend.to_dict(orient="records") if not trend.empty else [],
        "department_no_show_rates": dept_no_show.to_dict(orient="records") if not dept_no_show.empty else [],
    }
    user_content = (
        "The user asked a question about the hospital. Interpret and answer using ONLY the data below. "
        "Do not generate raw predictions or invent numbers. Reference thresholds (e.g. readmission ≥ 0.6, ICU ≥ 90%) where relevant.\n\n"
        f"User question: {query}\n\nData:\n" + json.dumps(data, default=str)
    )
    return _call_llm(_SYSTEM_PROMPT, user_content, max_tokens=1024)
