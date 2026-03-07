"""
Layer 4 — LLM Insight Engine

This module integrates with an LLM via an OpenAI-compatible API to provide
decision support. The AI does NOT generate raw predictions; it INTERPRETS
risk scores, SUMMARIZES trends, and SUGGESTS operational actions based only
on supplied structured data from the analytics layer (no fabricated numbers).
"""

import json
import os
from html import escape
from typing import Any, Optional

import pandas as pd

from hospital_analytics import (
    get_total_patients,
    get_icu_occupancy,
    get_high_readmission_patients,
    get_likely_no_shows,
    get_admissions_trend,
    get_department_no_show_rates,
    get_patient_history,
    predict_icu_capacity_reach_90,
    get_similar_patients,
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


# ---- HTML Report + AI Summary for 3-Question Dashboard ----

def _html_report_readmission(df: pd.DataFrame, limit: int) -> str:
    """Build HTML report for Q1: highest readmission risk patients."""
    parts = [
        '<div class="report-section">',
        '<h4>Highest 30-Day Readmission Risk Patients</h4>',
        '<p>Patients flagged with readmission risk ≥ 0.6 (hospital threshold).</p>',
    ]
    if df.empty:
        parts.append('<p class="text-muted">No high-risk patients in cohort.</p>')
    else:
        cols = [c for c in ["patient_id", "readmission_risk", "icu_risk", "no_show_risk", "age", "primary_diagnosis"] if c in df.columns]
        cols = cols or list(df.columns)[:6]
        parts.append('<div class="table-responsive"><table class="table table-hover"><thead><tr>')
        parts.extend(f'<th>{escape(str(c))}</th>' for c in cols)
        parts.append('</tr></thead><tbody>')
        for _, row in df.head(limit).iterrows():
            parts.append("<tr>" + "".join(f'<td>{escape(str(row.get(c, "")))}</td>' for c in cols) + "</tr>")
        parts.append("</tbody></table></div>")
    parts.append("</div>")
    return "\n".join(parts)


def summarize_readmission_page(df: pd.DataFrame, limit: int = 15) -> str:
    """AI summary for Q1 page. Returns markdown-style text."""
    data = df.head(limit).to_dict(orient="records") if not df.empty else []
    prompt = "Summarize the key findings from this high readmission-risk patient list. Use 3-5 bullet points. Highlight top risks and suggest 2-3 actionable recommendations. Use ONLY the data provided.\n\n" + json.dumps(data, default=str)
    return _call_llm(_SYSTEM_PROMPT, prompt)


def _html_report_icu(pred: dict, icu: dict) -> str:
    """Build HTML report for Q2: ICU capacity forecast."""
    status = "danger" if pred.get("already_at_risk") else "warning" if pred.get("estimated_days") and pred["estimated_days"] < 3 else "info"
    parts = [
        '<div class="report-section">',
        '<h4>ICU Capacity Forecast — When Will We Reach 90%?</h4>',
        f'<div class="alert alert-{status}">',
        f'<strong>Current:</strong> {pred.get("current_occupied", 0)} / {pred.get("total_beds", 50)} beds '
        f'({pred.get("current_occupied", 0) / max(1, pred.get("total_beds", 50)) * 100:.1f}%)',
        '</div>',
        f'<p><strong>Forecast:</strong> {escape(str(pred.get("forecast_note", "N/A")))}</p>',
    ]
    if pred.get("estimated_days") and not pred.get("already_at_risk"):
        parts.append(f'<p><strong>Estimated days to 90%:</strong> ~{pred["estimated_days"]:.0f} days</p>')
    parts.append("</div>")
    return "\n".join(parts)


def summarize_icu_page(pred: dict, icu: dict, trend_data: list) -> str:
    """AI summary for Q2 page."""
    data = {"icu_occupancy": icu, "forecast": pred, "recent_trend_sample": trend_data[:14]}
    prompt = "Summarize ICU capacity and forecast. Use 3-5 bullet points. Suggest 2-3 operational actions. Use ONLY the data provided.\n\n" + json.dumps(data, default=str)
    return _call_llm(_SYSTEM_PROMPT, prompt)


def _html_report_comparison(sim: dict) -> str:
    """Build HTML report for Q3: patient comparison."""
    parts = [
        '<div class="report-section">',
        f'<h4>Patient {escape(str(sim.get("patient_id", "")))} — Similar Historical Cases</h4>',
        '<p>Similarity based on readmission, ICU, and no-show risk scores.</p>',
    ]
    profile = sim.get("patient_profile", {})
    if profile:
        parts.append('<h5>This Patient</h5><ul class="list-unstyled">')
        for k, v in list(profile.items())[:8]:
            if v is not None and str(v) and k not in ("_dist",):
                parts.append(f"<li><strong>{escape(str(k))}:</strong> {escape(str(v))}</li>")
        parts.append("</ul>")
    similar = sim.get("similar", [])
    if similar:
        parts.append('<h5>Similar Cases</h5><table class="table table-sm"><thead><tr><th>Patient</th><th>Readmission</th><th>ICU</th><th>No-Show</th><th>Age</th></tr></thead><tbody>')
        for s in similar:
            parts.append(f"<tr><td>{escape(str(s.get('patient_id','')))}</td><td>{s.get('readmission_risk','')}</td><td>{s.get('icu_risk','')}</td><td>{s.get('no_show_risk','')}</td><td>{s.get('age','')}</td></tr>")
        parts.append("</tbody></table>")
    else:
        parts.append(f'<p class="text-muted">{escape(sim.get("note", "No similar cases."))}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def summarize_comparison_page(sim: dict) -> str:
    """AI summary for Q3 page."""
    prompt = "Compare this patient to similar historical cases. Use 3-5 bullet points. Suggest care considerations. Use ONLY the data provided.\n\n" + json.dumps(sim, default=str)
    return _call_llm(_SYSTEM_PROMPT, prompt)


def summarize_vitals_page(vitals_summary: dict) -> str:
    """AI summary for post-discharge vitals. Focus on what stakeholders should do."""
    prompt = (
        "Post-discharge vitals data (from monitors/sensors). Summarize in 3-5 bullet points. "
        "Tell stakeholders: (1) what the vitals indicate, (2) any concerning patterns, (3) 2-3 specific actions to take. "
        "Use ONLY the data provided. Be actionable.\n\n" + json.dumps(vitals_summary, default=str)
    )
    return _call_llm(_SYSTEM_PROMPT, prompt)
