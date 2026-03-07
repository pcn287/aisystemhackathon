"""
Layer 4 — LLM Insight Engine

This module integrates with an LLM via an OpenAI-compatible API to provide
decision support. All functions accept data_context (from get_system_strain)
so KPIs and AI use identical numbers. No raw predictions; interprets supplied data.
"""

import json
import os
import time
from typing import Any, Optional

from hospital_analytics import (
    get_admissions_trend,
    get_department_no_show_rates,
    get_high_readmission_patients,
    get_patient_history,
)

_OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
_LLM_TIMEOUT_SEC = 10
_CACHE_TTL_SEC = 60
_response_cache: dict[str, tuple[float, str]] = {}

_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
if not _key or not str(_key).strip().startswith("sk-"):
    print("[AI Agent] WARNING: OPENAI_API_KEY missing or invalid")
    print("[AI Agent] AI features will return placeholder text")
    _AI_AVAILABLE = False
else:
    _AI_AVAILABLE = True

if not (os.environ.get("OPENAI_BASE_URL") or "").strip().startswith("http"):
    os.environ.pop("OPENAI_BASE_URL", None)


def _get_client():
    try:
        from openai import OpenAI
    except ImportError:
        return None
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    raw = os.environ.get("OPENAI_BASE_URL") or ""
    base_url = raw.strip() if isinstance(raw, str) else ""
    if not base_url or not (base_url.startswith("http://") or base_url.startswith("https://")):
        base_url = _OPENAI_DEFAULT_BASE
        if "OPENAI_BASE_URL" in os.environ:
            del os.environ["OPENAI_BASE_URL"]
    return OpenAI(api_key=api_key, base_url=base_url, timeout=_LLM_TIMEOUT_SEC)


def _as_list(val: Any) -> list[Any]:
    """Normalize None/DataFrame/list-like values to a JSON-serializable list."""
    if val is None:
        return []
    if hasattr(val, "empty") and hasattr(val, "to_dict"):
        try:
            return [] if val.empty else val.to_dict(orient="records")
        except Exception:
            return []
    if isinstance(val, list):
        return val
    if isinstance(val, tuple):
        return list(val)
    return []


def _safe_len(val: Any) -> int:
    if val is None:
        return 0
    if hasattr(val, "empty") and hasattr(val, "__len__"):
        try:
            return 0 if val.empty else len(val)
        except Exception:
            return 0
    try:
        return len(val)
    except Exception:
        return 0


def _call_llm(system_prompt: str, user_content: str, max_tokens: int = 1024) -> str:
    """Call LLM with 10s timeout. Returns response or fallback string."""
    client = _get_client()
    if client is None:
        return (
            "LLM not available. Set OPENAI_API_KEY (or LLM_API_KEY) and optionally OPENAI_BASE_URL."
        )
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    def do_create(c):
        return c.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, timeout=_LLM_TIMEOUT_SEC
        )

    try:
        r = do_create(client)
        if r.choices and len(r.choices) > 0:
            return (r.choices[0].message.content or "").strip()
    except Exception as e:
        err_str = str(e).lower()
        if "connection" in err_str or "protocol" in err_str or "base_url" in err_str or "timeout" in err_str:
            try:
                from openai import OpenAI
                api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
                fallback = OpenAI(api_key=api_key, base_url=_OPENAI_DEFAULT_BASE, timeout=_LLM_TIMEOUT_SEC)
                r = do_create(fallback)
                if r.choices and len(r.choices) > 0:
                    return (r.choices[0].message.content or "").strip()
            except Exception:
                pass
        return f"Error calling LLM (timeout or connection): {e}"
    return "No response from model."


def _cached_call(cache_key: str, fn, *args, **kwargs) -> str:
    """Return cached response if same key within _CACHE_TTL_SEC."""
    now = time.time()
    if cache_key in _response_cache:
        ts, resp = _response_cache[cache_key]
        if now - ts < _CACHE_TTL_SEC:
            return resp
    out = fn(*args, **kwargs)
    _response_cache[cache_key] = (now, out)
    return out


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


def generate_operational_summary(data_context: dict) -> str:
    """
    Generate operational summary using ONLY the provided data_context (from get_system_strain).
    This ensures the AI uses the same numbers as the dashboard KPIs.
    """
    if not _AI_AVAILABLE:
        icu = data_context.get("icu_occupied", 0)
        total = data_context.get("icu_total", 50)
        score = data_context.get("strain_score", 0)
        return (
            f"ICU at {icu}/{total} beds. "
            f"System strain score: {score:.0f}/100. "
            "AI analysis unavailable — check OPENAI_API_KEY."
        )
    try:
        def _do():
            data = {
                "hospital_profile": _HOSPITAL_PROFILE,
                "strain": data_context,
                "high_readmission_patient_count": data_context.get("high_readmission_count", 0),
                "likely_no_shows_tomorrow_count": data_context.get("likely_no_show_count", 0),
            }
            trend = _as_list(data_context.get("admissions_trend_records"))
            dept = _as_list(data_context.get("department_no_show_records"))
            data["admissions_trend_last_7_days"] = trend
            data["department_no_show_rates"] = dept[:10]
            user_content = (
                "Using ONLY the data below, write a brief operational summary (2–4 sentences). "
                "Reference hospital profile thresholds where relevant. Use the exact counts in the data.\n\n"
                + json.dumps(data, default=str)
            )
            return _call_llm(_SYSTEM_PROMPT, user_content)

        key = "summary:" + json.dumps(data_context, default=str, sort_keys=True)[:500]
        return _cached_call(key, _do)
    except Exception as e:
        return f"AI temporarily unavailable: {e}"


def explain_patient_risk(patient_id: str | int, history: dict) -> str:
    """
    Explain risk for a specific patient using the supplied history dict (from get_patient_history).
    """
    if not _AI_AVAILABLE:
        n_adm = _safe_len(history.get("admissions"))
        return f"Patient {patient_id}: {n_adm} admission(s) in history. AI explanation unavailable — check OPENAI_API_KEY."
    try:
        def _do():
            import pandas as pd
            rs = history.get("risk_scores")
            risk_records = rs.to_dict(orient="records") if rs is not None and hasattr(rs, "empty") and not rs.empty else []
            data = {
                "hospital_profile": _HOSPITAL_PROFILE,
                "demographics": history.get("demographics", {}),
                "admissions_count": _safe_len(history.get("admissions")),
                "vitals_records_count": _safe_len(history.get("vitals")),
                "risk_scores": risk_records,
            }
            user_content = (
                f"Using ONLY the data below for patient_id={patient_id}, interpret this patient's risk profile "
                "(readmission ≥ 0.6 is flagged; mention vitals only if present). Do not invent numbers.\n\n"
                + json.dumps(data, default=str)
            )
            return _call_llm(_SYSTEM_PROMPT, user_content)

        rs = history.get("risk_scores")
        rs_len = len(rs) if rs is not None and hasattr(rs, "__len__") else 0
        key = f"explain:{patient_id}:{len(history.get('admissions', []))}:{rs_len}"[:200]
        return _cached_call(key, _do)
    except Exception as e:
        return f"AI temporarily unavailable: {e}"


def predict_capacity_alerts(data_context: dict) -> str:
    """Generate capacity-related alerts using the supplied data_context."""
    if not _AI_AVAILABLE:
        total = data_context.get("icu_total", 50)
        occupied = data_context.get("icu_occupied", 0)
        rate = data_context.get("icu_rate", 0)
        return f"ICU {occupied}/{total} beds ({rate*100:.0f}% occupancy). AI alerts unavailable — check OPENAI_API_KEY."
    try:
        def _do():
            data = {
                "hospital_profile": _HOSPITAL_PROFILE,
                "icu_occupancy": {
                    "total": data_context.get("icu_total", 0),
                    "occupied": data_context.get("icu_occupied", 0),
                    "rate": data_context.get("icu_rate", 0),
                },
                "admissions_trend": _as_list(data_context.get("admissions_trend_records")),
            }
            user_content = (
                "Using ONLY the data below, summarize ICU capacity. ICU occupancy ≥ 90% is high operational risk (50 beds). "
                "Suggest actions if needed. Do not invent numbers.\n\n" + json.dumps(data, default=str)
            )
            return _call_llm(_SYSTEM_PROMPT, user_content)

        key = "capacity:" + json.dumps({k: data_context.get(k) for k in ("icu_rate", "icu_total", "icu_occupied")}, sort_keys=True)
        return _cached_call(key, _do)
    except Exception as e:
        return f"AI temporarily unavailable: {e}"


def answer_user_question(question: str, data_context: dict) -> str:
    """
    Answer a natural language question using ONLY the supplied data_context.
    This ensures answers use the same numbers as the dashboard.
    """
    if not _AI_AVAILABLE:
        return (
            "AI answers unavailable — check OPENAI_API_KEY. "
            "Use the dashboard KPIs and charts for data."
        )
    try:
        def _do():
            data = {
                "hospital_profile": _HOSPITAL_PROFILE,
                "strain": data_context,
                "high_readmission_count": data_context.get("high_readmission_count", 0),
                "likely_no_show_count": data_context.get("likely_no_show_count", 0),
                "admissions_trend": _as_list(data_context.get("admissions_trend_records")),
                "department_no_show_rates": _as_list(data_context.get("department_no_show_records")),
            }
            user_content = (
                "The user asked a question about the hospital. Interpret and answer using ONLY the data below. "
                "Do not generate raw predictions or invent numbers. Reference thresholds (e.g. readmission ≥ 0.6, ICU ≥ 90%) where relevant.\n\n"
                f"User question: {question}\n\nData:\n" + json.dumps(data, default=str)
            )
            return _call_llm(_SYSTEM_PROMPT, user_content, max_tokens=1024)

        key = "answer:" + question.strip()[:100] + ":" + json.dumps(data_context, default=str, sort_keys=True)[:400]
        return _cached_call(key, _do)
    except Exception as e:
        return f"AI temporarily unavailable: {e}"


def generate_operational_recommendations(summary_data: dict) -> str:
    """
    LLM-generated actionable recommendations for hospital administrators.
    summary_data should include: icu_occupancy (or icu_rate, icu_occupied, icu_total),
    high_readmission_count, likely_no_show_count (or similar).
    """
    if not _AI_AVAILABLE:
        return (
            "AI recommendations unavailable — check OPENAI_API_KEY. "
            "Review ICU capacity, high readmission list, and no-show risk in the dashboard."
        )
    try:
        def _do():
            user_content = (
                "You are a hospital operations assistant.\n\n"
                "Given these hospital metrics:\n"
                f"ICU occupancy: {summary_data.get('icu_rate', summary_data.get('icu_occupancy', 0)) * 100:.0f}% "
                f"({summary_data.get('icu_occupied', 0)}/{summary_data.get('icu_total', 50)} beds)\n"
                f"High readmission patients: {summary_data.get('high_readmission_count', 0)}\n"
                f"Likely no-shows: {summary_data.get('likely_no_show_count', summary_data.get('likely_noshows', 0))}\n\n"
                "Provide 3 actionable operational recommendations that hospital administrators should take today. "
                "Each recommendation should include: action, reason, and expected impact. "
                "Use short bullet points; be specific and practical."
            )
            return _call_llm(_SYSTEM_PROMPT, user_content, max_tokens=800)

        key = "recs:" + json.dumps({k: summary_data.get(k) for k in ("icu_rate", "high_readmission_count", "likely_no_show_count")}, sort_keys=True)
        return _cached_call(key, _do)
    except Exception as e:
        return f"AI temporarily unavailable: {e}"


def generate_situation_brief(summary_data: dict) -> str:
    """
    One-paragraph executive summary of the whole dashboard (ICU, readmission, no-show, strain).
    Hospital executives use this as the AI Hospital Situation Brief.
    """
    if not _AI_AVAILABLE:
        icu = summary_data.get("icu_occupied", 0)
        total = summary_data.get("icu_total", 50)
        return (
            f"ICU at {icu}/{total} beds. "
            "AI situation brief unavailable — check OPENAI_API_KEY."
        )
    try:
        def _do():
            user_content = (
                "You are a hospital operations assistant. Summarize the current hospital situation in ONE short paragraph "
                "(3–5 sentences) for executives. Include: ICU occupancy and trend, readmission risk level, no-show risk, "
                "and one or two immediate priorities (e.g. bed management, follow-up outreach). "
                "Use ONLY the numbers provided; do not invent data. Be concise and actionable.\n\n"
                + json.dumps(summary_data, default=str)
            )
            return _call_llm(_SYSTEM_PROMPT, user_content, max_tokens=400)

        key = "brief:" + json.dumps(summary_data, default=str, sort_keys=True)[:600]
        return _cached_call(key, _do)
    except Exception as e:
        return f"AI temporarily unavailable: {e}"


def patient_digital_twin_insight(patient_id: str | int, history: dict) -> str:
    """
    LLM interpretation for Patient Digital Twin: readmission probability, risk factors, suggested follow-up.
    """
    if not _AI_AVAILABLE:
        return (
            f"Patient {patient_id}: AI insight unavailable — check OPENAI_API_KEY. "
            "Use risk scores and vitals in the dashboard."
        )
    try:
        def _do():
            rs = history.get("risk_scores")
            risk_records = _as_list(rs)
            data = {
                "patient_id": patient_id,
                "demographics": history.get("demographics", {}),
                "admissions_count": _safe_len(history.get("admissions")),
                "vitals_count": _safe_len(history.get("vitals")),
                "risk_scores": risk_records,
            }
            user_content = (
                "You are a clinical risk assistant. Given the following patient data, explain:\n"
                "1. Readmission probability (use risk_scores if present)\n"
                "2. Key clinical risk factors\n"
                "3. Suggested follow-up intervention\n\n"
                "Do not invent numbers. Use only the data below.\n\n"
                + json.dumps(data, default=str)
            )
            return _call_llm(_SYSTEM_PROMPT, user_content, max_tokens=600)

        key = f"twin:{patient_id}:{len(history.get('admissions', []))}"[:150]
        return _cached_call(key, _do)
    except Exception as e:
        return f"AI temporarily unavailable: {e}"
