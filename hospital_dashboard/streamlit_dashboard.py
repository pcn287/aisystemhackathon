"""
Hospital Operations Command Center — Streamlit Dashboard

Uses hospital_analytics, database_connection, and optional LLM (hospital_ai_agent).
Run: streamlit run streamlit_dashboard.py
Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY); optional OPENAI_API_KEY.
"""

import html as html_module
import os
import pandas as pd
import streamlit as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hospital_analytics import (
    get_system_strain,
    get_high_readmission_patients,
    get_likely_no_shows,
    get_admissions_trend,
    get_department_no_show_rates,
    get_patient_id_list,
    get_patient_history,
)
from hospital_ai_agent import answer_user_question, explain_patient_risk
from database_connection import get_patients, get_risk_scores, get_icu_beds
from data_queries import get_trend_data
from analytics import analyze_readmission_drivers, hospital_strain_score
from forecasting import predict_icu_load
from llm_insights import (
    generate_operational_recommendations,
    generate_situation_brief,
    patient_digital_twin_insight,
)


def _records_to_df(records):
    """Convert list of dicts to pandas DataFrame. Returns empty DataFrame if invalid."""
    if records is None or not isinstance(records, list):
        return pd.DataFrame()
    if not records:
        return pd.DataFrame()
    try:
        return pd.DataFrame(records)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_strain():
    return get_system_strain()


@st.cache_data(ttl=60)
def load_readmission(limit=100):
    return get_high_readmission_patients(limit=limit)


@st.cache_data(ttl=60)
def load_trend(days=30):
    return get_admissions_trend(days=days)


@st.cache_data(ttl=60)
def load_noshow_dept():
    return get_department_no_show_rates()


@st.cache_data(ttl=60)
def load_noshow_patients():
    return get_likely_no_shows()


@st.cache_data(ttl=60)
def load_patient_ids():
    return get_patient_id_list()


@st.cache_data(ttl=60)
def load_trend_data(metric_name: str, days_7: bool = True):
    """Cached trend data for ICU, readmission, no-show."""
    try:
        return get_trend_data(metric_name, days_7=days_7)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_patients_table():
    """Build merged patient list: patients + risk_scores + icu_status (for drill-down lists)."""
    try:
        patients = get_patients()
        risk = get_risk_scores()
        icu = get_icu_beds()
        if patients is None or patients.empty:
            return pd.DataFrame()
        df = patients.copy()
        pid_col = "patient_id" if "patient_id" in df.columns else df.columns[0]
        if risk is not None and not risk.empty and "patient_id" in risk.columns:
            risk_sub = risk[[c for c in risk.columns if c in ["patient_id", "readmission_risk", "no_show_risk", "icu_risk"]]].drop_duplicates(subset=["patient_id"], keep="last")
            df = df.merge(risk_sub, on="patient_id", how="left", suffixes=("", "_risk"))
        if icu is not None and not icu.empty and "patient_id" in icu.columns:
            occ_col = "is_occupied" if "is_occupied" in icu.columns else "occupied"
            if occ_col in icu.columns:
                occupied_beds = icu[icu[occ_col] == True]
            else:
                occupied_beds = icu
            icu_ids = set(occupied_beds["patient_id"].dropna().astype(str).unique())
            df["icu_status"] = df[pid_col].astype(str).map(lambda x: "Yes" if x in icu_ids else "No")
        else:
            df["icu_status"] = "No"
        return df
    except Exception:
        return pd.DataFrame()


def _plotly_layout():
    return dict(
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F6F8FB",
        font=dict(color="#1A1A1A"),
        margin=dict(t=30, b=40, l=50, r=20),
        xaxis=dict(gridcolor="#E5E7EB", showgrid=True),
        yaxis=dict(gridcolor="#E5E7EB", showgrid=True),
        legend=dict(bgcolor="#FFFFFF", bordercolor="#E5E7EB"),
    )


def _render_drilldown_page(strain, diagnosis_filter):
    """Render patient list or patient twin page based on st.session_state.page."""
    page = st.session_state.page
    if page == "patient_twin" and st.session_state.patient_twin_id:
        _render_patient_twin(strain, st.session_state.patient_twin_id)
        return
    # Patient list pages
    try:
        df = load_patients_table()
    except Exception as e:
        st.error(f"Failed to load patients: {e}")
        df = pd.DataFrame()
    if df.empty:
        st.warning("No patient data available.")
        return
    # Apply list-type filter
    if page == "icu_patients" and "icu_status" in df.columns:
        df = df[df["icu_status"].astype(str).str.lower() == "yes"]
    elif page == "readmission_risk":
        try:
            high_df = load_readmission(limit=500)
            if high_df is not None and not high_df.empty and "patient_id" in high_df.columns:
                ids = set(high_df["patient_id"].astype(str))
                pid_col = "patient_id" if "patient_id" in df.columns else df.columns[0]
                df = df[df[pid_col].astype(str).isin(ids)]
        except Exception:
            pass
    elif page == "no_shows":
        try:
            noshow_df = load_noshow_patients()
            if noshow_df is not None and not noshow_df.empty and "patient_id" in noshow_df.columns:
                ids = set(noshow_df["patient_id"].astype(str))
                pid_col = "patient_id" if "patient_id" in df.columns else df.columns[0]
                df = df[df[pid_col].astype(str).isin(ids)]
        except Exception:
            pass
    # Sidebar filters
    age_col = None
    for c in ["age", "date_of_birth", "dob"]:
        if c in df.columns:
            age_col = c
            break
    if age_col and age_col == "age":
        df = df[(df["age"] >= st.session_state.sidebar_age_min) & (df["age"] <= st.session_state.sidebar_age_max)]
    if diagnosis_filter and diagnosis_filter.strip():
        diag_col = next((c for c in df.columns if "diagn" in c.lower() or "condition" in c.lower()), None)
        if diag_col is not None:
            df = df[df[diag_col].astype(str).str.lower().str.contains(diagnosis_filter.strip().lower(), na=False)]
    if st.session_state.sidebar_high_risk_only and "readmission_risk" in df.columns:
        df = df[df["readmission_risk"] >= 0.6]
    if st.session_state.sidebar_icu_only and "icu_status" in df.columns:
        df = df[df["icu_status"].astype(str).str.lower() == "yes"]
    # Title
    titles = {"patients": "All Patients", "icu_patients": "ICU Patients", "readmission_risk": "High Readmission Risk", "no_shows": "Likely No-Shows"}
    st.markdown(f"#### {titles.get(page, 'Patients')}")
    # Search
    search = st.text_input("Search (patient ID, name, diagnosis)", key="list_search")
    if search and search.strip():
        pid_col = "patient_id" if "patient_id" in df.columns else df.columns[0]
        mask = df.astype(str).apply(lambda row: row.str.contains(search.strip(), case=False, na=False).any(), axis=1)
        df = df[mask]
    # Patient selection dropdown
    pid_col = "patient_id" if "patient_id" in df.columns else df.columns[0]
    ids = [""] + df[pid_col].astype(str).unique().tolist()[:500]
    selected = st.selectbox("Select patient", ids, format_func=lambda x: "Select patient..." if x == "" else x, key="list_select")
    if st.button("Open Digital Twin", type="primary", key="open_twin_btn") and selected:
        st.session_state.patient_twin_id = selected
        st.session_state.page = "patient_twin"
        st.rerun()
    # Table
    preferred = ["patient_id", "age", "gender", "diagnosis", "heart_rate", "blood_pressure", "oxygen_saturation", "oxygen", "icu_status", "readmission_risk", "no_show_risk"]
    display_cols = [c for c in preferred if c in df.columns]
    if not display_cols:
        display_cols = list(df.columns)[:12]
    st.dataframe(df[display_cols].head(200) if display_cols else df.head(200), use_container_width=True, hide_index=True)


def _render_patient_twin(strain, patient_id):
    """Single patient Digital Twin view with vitals, risk, and AI explanation."""
    st.markdown(f"#### Patient Digital Twin — {patient_id}")
    try:
        hist = get_patient_history(patient_id)
    except Exception as e:
        st.error(f"Failed to load patient: {e}")
        return
    dem = hist.get("demographics", {})
    risk_scores = hist.get("risk_scores", pd.DataFrame())
    vitals = hist.get("vitals", pd.DataFrame())
    admissions = hist.get("admissions", pd.DataFrame())
    # Patient info
    st.markdown("**Patient Information**")
    if dem:
        cols = st.columns(3)
        items = list(dem.items())
        for i, (k, v) in enumerate(items[:9]):
            cols[i % 3].metric(k.replace("_", " ").title(), str(v))
    else:
        st.caption("No demographics.")
    # Vitals
    st.markdown("**Vitals**")
    if vitals is not None and not vitals.empty:
        v = vitals.tail(20)
        num_cols = v.select_dtypes(include="number").columns.tolist()
        if num_cols:
            st.line_chart(v[num_cols[:4]] if len(num_cols) >= 4 else v[num_cols])
        st.dataframe(v.tail(10), use_container_width=True, hide_index=True)
    else:
        st.caption("No vitals.")
    # Risk scores
    st.markdown("**Risk Scores**")
    if risk_scores is not None and not risk_scores.empty:
        for c in risk_scores.columns:
            if c == "patient_id":
                continue
            val = risk_scores[c].iloc[0]
            color = "#DC2626" if val >= 0.8 else "#F59E0B" if val >= 0.5 else "#16A34A"
            st.metric(c.replace("_", " ").title(), f"{float(val):.2f}")
    else:
        st.caption("No risk scores.")
    # ICU status
    st.markdown("**ICU status**")
    icu_occupied = strain.get("icu_occupied", 0)
    st.caption(f"ICU occupancy: {icu_occupied} / {strain.get('icu_total', 50)} beds.")
    # AI Risk Explanation
    st.markdown("**AI Risk Explanation**")
    with st.spinner("Generating explanation..."):
        try:
            explanation = explain_patient_risk(patient_id, hist)
            st.markdown(explanation)
        except Exception as e:
            st.warning("AI insights temporarily unavailable.")
    # Patient Digital Twin Insight (readmission probability, risk factors, follow-up)
    st.markdown("**Patient Digital Twin Insight**")
    with st.spinner("Generating insight..."):
        try:
            twin_insight = patient_digital_twin_insight(patient_id, hist)
            st.markdown(twin_insight)
        except Exception as e:
            st.warning("AI insights temporarily unavailable.")
    if admissions is not None and not admissions.empty:
        st.markdown("**Admission History**")
        st.dataframe(admissions, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(
        page_title="Hospital Operations Command Center",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Navigation state
    if "page" not in st.session_state:
        st.session_state.page = "dashboard"
    if "patient_twin_id" not in st.session_state:
        st.session_state.patient_twin_id = None
    if "sidebar_age_min" not in st.session_state:
        st.session_state.sidebar_age_min = 0
    if "sidebar_age_max" not in st.session_state:
        st.session_state.sidebar_age_max = 120
    if "sidebar_icu_only" not in st.session_state:
        st.session_state.sidebar_icu_only = False
    if "sidebar_high_risk_only" not in st.session_state:
        st.session_state.sidebar_high_risk_only = False
    if "sidebar_risk_min" not in st.session_state:
        st.session_state.sidebar_risk_min = 0.6
    if "sidebar_risk_max" not in st.session_state:
        st.session_state.sidebar_risk_max = 1.0
    if "sidebar_readmit_dept" not in st.session_state:
        st.session_state.sidebar_readmit_dept = "All"

    # Load strain first (used in navbar and throughout)
    try:
        strain = load_strain()
    except Exception as e:
        st.error("Unable to load hospital data.")
        st.caption(str(e))
        st.stop()

    # ─── CSS Theme (light, professional healthcare) ─────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
    
    /* Main app: light neutral background */
    .stApp {
        background-color: #F6F8FB;
        font-family: 'DM Sans', sans-serif;
        color: #1A1A1A;
    }
    
    /* Sidebar: white card, subtle border */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E5E7EB;
    }
    [data-testid="stSidebar"] .stMarkdown { color: #1A1A1A; }
    
    /* Tabs: light bar, medical blue accent */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #FFFFFF;
        border-bottom: 1px solid #E5E7EB;
        padding: 0 16px;
        gap: 4px;
        border-radius: 12px 12px 0 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .stTabs [data-baseweb="tab"] {
        color: #6B7280;
        font-size: 0.85rem;
        font-weight: 500;
        padding: 12px 20px;
        border-radius: 8px 8px 0 0;
        border-bottom: 2px solid transparent;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #1F4E79 !important;
        border-bottom: 2px solid #3A7BD5 !important;
        background: transparent !important;
    }
    
    /* KPI / metric cards: white, soft shadow, readable hierarchy */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    [data-testid="stMetricLabel"] {
        color: #6B7280;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    [data-testid="stMetricValue"] {
        color: #1A1A1A;
        font-family: 'DM Mono', monospace;
        font-size: 36px;
        font-weight: 600;
    }
    
    /* Cards: white container, rounded, soft shadow */
    .hd-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .hd-card-title {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #6B7280;
        margin-bottom: 12px;
    }
    
    /* Banners: success / warning / danger */
    .banner-normal  { background:#16A34A; color:#fff; padding:16px 20px; border-radius:10px; margin-bottom:16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .banner-caution { background:#F59E0B; color:#1A1A1A; padding:16px 20px; border-radius:10px; margin-bottom:16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .banner-critical{ background:#DC2626; color:#fff; padding:16px 20px; border-radius:10px; margin-bottom:16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); animation: pulse 1.5s infinite; }
    
    /* Tables */
    .hd-table { width:100%; border-collapse:collapse; font-size:0.85rem; }
    .hd-table th { background:#F6F8FB; color:#6B7280; padding:8px 12px; text-align:left; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.05em; border-bottom:1px solid #E5E7EB; }
    .hd-table td { padding:8px 12px; border-bottom:1px solid #E5E7EB; color:#1A1A1A; }
    .hd-table tr:hover td { background:#F6F8FB; }
    
    /* Risk badges */
    .risk-critical { background:#DC2626; color:#fff; padding:3px 10px; border-radius:20px; font-size:0.75rem; font-family:'DM Mono',monospace; }
    .risk-high     { background:#F59E0B; color:#1A1A1A; padding:3px 10px; border-radius:20px; font-size:0.75rem; font-family:'DM Mono',monospace; }
    .risk-moderate { background:#3A7BD5; color:#fff; padding:3px 10px; border-radius:20px; font-size:0.75rem; font-family:'DM Mono',monospace; }
    
    /* Bed grid: occupied = red, free = green */
    .bed-grid { display:grid; grid-template-columns:repeat(10, 36px); gap:6px; }
    .bed-occ  { width:36px; height:36px; background:#DC2626; border-radius:6px; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
    .bed-free { width:36px; height:36px; background:#16A34A; border-radius:6px; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
    
    /* Buttons: medical blue, rounded */
    .stButton > button {
        background-color: #3A7BD5 !important;
        color: #FFFFFF !important;
        border-radius: 8px;
        border: none;
        font-weight: 500;
    }
    .stButton > button:hover {
        background-color: #1F4E79 !important;
        color: #FFFFFF !important;
    }
    
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
    .block-container { padding-top: 1rem; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.85; } }
    </style>
    """, unsafe_allow_html=True)

    # ─── Top Navbar (gradient header) ──────────────────────────────────────
    strain_color = "#DC2626" if strain.get("strain_level") == "critical" else "#F59E0B" if strain.get("strain_level") == "elevated" else "#16A34A"
    st.markdown(f"""
    <div style="display:flex; align-items:center; justify-content:space-between;
                padding:16px 24px; background: linear-gradient(90deg, #1F4E79, #3A7BD5);
                border-radius: 12px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
        <div style="display:flex; align-items:center; gap:12px;">
            <span style="font-size:1.5rem;">🏥</span>
            <span style="font-weight:700; font-size:1.1rem; color:#FFFFFF;">
                Hospital Operations Command Center
            </span>
        </div>
        <div style="color:rgba(255,255,255,0.95); font-size:0.8rem;">
            Data as of: {strain.get('data_as_of', 'unknown')} &nbsp;|&nbsp;
            Strain: <span style="color:{strain_color}; font-weight:600;">{str(strain.get('strain_level', 'unknown')).upper()}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Extract common metrics
    icu_rate = (strain.get("icu_rate") or 0) * 100
    strain_score = strain.get("strain_score") or 0
    total_patients = strain.get("total_patients") or 0
    high_readmit = strain.get("high_readmission_count") or 0
    likely_noshows = strain.get("likely_no_show_count") or 0
    readmit_rate = (strain.get("readmit_rate") or 0) * 100
    noshow_rate = (strain.get("noshow_rate") or 0) * 100
    icu_occupied = strain.get("icu_occupied") or 0
    icu_total = strain.get("icu_total") or 50
    discharge_pending = strain.get("discharge_pending") or 0

    # Operational Risk Score (decision support formula: 0.5*ICU + 0.3*readmit + 0.2*noshow)
    op_score, op_status = hospital_strain_score(
        icu_rate / 100.0, (readmit_rate / 100.0) if total_patients else 0, (noshow_rate / 100.0) if total_patients else 0
    )
    if op_status == "normal":
        st.success(f"**Hospital Strain Score: {op_score:.0f}/100** — Status: {op_status.capitalize()}")
    elif op_status == "elevated":
        st.warning(f"**Hospital Strain Score: {op_score:.0f}/100** — Status: {op_status.capitalize()}")
    else:
        st.error(f"**Hospital Strain Score: {op_score:.0f}/100** — Status: {op_status.capitalize()}")

    # ─── Sidebar: navigation + filters ─────────────────────────────────────
    with st.sidebar:
        st.markdown("### Navigation")
        if st.session_state.page != "dashboard":
            if st.button("← Back to Dashboard", type="primary", use_container_width=True):
                st.session_state.page = "dashboard"
                st.session_state.patient_twin_id = None
                st.rerun()
        st.markdown("---")
        st.markdown("### Filters (patient lists)")
        age_min = st.number_input("Age min", 0, 120, int(st.session_state.sidebar_age_min), key="age_min")
        age_max = st.number_input("Age max", 0, 120, int(st.session_state.sidebar_age_max) or 120, key="age_max")
        st.session_state.sidebar_age_min = age_min
        st.session_state.sidebar_age_max = age_max
        icu_only = st.checkbox("ICU patients only", value=st.session_state.sidebar_icu_only, key="icu_only")
        high_risk_only = st.checkbox("High readmission risk only", value=st.session_state.sidebar_high_risk_only, key="high_risk_only")
        st.session_state.sidebar_icu_only = icu_only
        st.session_state.sidebar_high_risk_only = high_risk_only
        diagnosis_filter = st.text_input("Diagnosis (contains)", key="diagnosis_filter")
        with st.expander("Readmission Risk filters"):
            risk_min = st.slider("Risk score min", 0.0, 1.0, float(st.session_state.sidebar_risk_min), 0.05, key="risk_min")
            risk_max = st.slider("Risk score max", 0.0, 1.0, float(st.session_state.sidebar_risk_max), 0.05, key="risk_max")
            st.session_state.sidebar_risk_min = risk_min
            st.session_state.sidebar_risk_max = risk_max
            try:
                _hr = load_readmission(limit=500)
                dept_options = ["All"]
                if _hr is not None and not _hr.empty:
                    for c in _hr.columns:
                        if "department" in c.lower() or "dept" in c.lower():
                            dept_options.extend(sorted(_hr[c].dropna().astype(str).unique().tolist()))
                            break
                sidebar_readmit_dept = st.selectbox("Department", dept_options, key="readmit_dept")
                st.session_state.sidebar_readmit_dept = sidebar_readmit_dept
            except Exception:
                pass
        st.markdown("---")
        st.markdown("### Debug")
        show_debug = st.checkbox("Show raw data", False, key="show_debug")

    # ─── Drill-down / Patient Twin pages (no tabs) ───────────────────────────
    if st.session_state.page != "dashboard":
        _render_drilldown_page(strain, diagnosis_filter)
        if show_debug:
            with st.sidebar:
                st.json(strain)
        st.markdown("---")
        st.markdown(
            f'<div style="text-align:center; color:#6B7280; font-size:0.75rem;">'
            f'Data as of {strain.get("data_as_of", "unknown")} | Hospital Digital Twin'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # ─── Tabs (Dashboard) ──────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🏠 Command Center",
        "🛏 ICU Capacity",
        "⚠️ Readmission Risk",
        "📅 No-Show Risk",
        "👤 Patient Twin",
        "📈 Trends",
        "🤖 AI Assistant",
    ])

    # ─── TAB 1: Command Center ────────────────────────────────────────────
    with tab1:
        # Section A: Health Banner
        if strain_score < 40:
            cls, msg = "banner-normal", "✅ SYSTEM OPERATING NORMALLY"
        elif strain_score <= 70:
            cls, msg = "banner-caution", "⚠️ ELEVATED STRAIN — MONITOR CLOSELY"
        else:
            cls, msg = "banner-critical", "🚨 HIGH STRAIN — ACTION REQUIRED"

        st.markdown(f"""
        <div class="{cls}">
            <div style="font-weight:700; font-size:1.1rem;">{msg}</div>
            <div style="margin-top:8px; font-size:0.85rem;">
                Strain Score: <strong>{strain_score:.0f}/100</strong> &nbsp;|&nbsp;
                ICU: {icu_rate:.0f}% &nbsp;|&nbsp;
                Readmit: {readmit_rate:.1f}% &nbsp;|&nbsp;
                No-Show: {noshow_rate:.1f}%
            </div>
        </div>
        """, unsafe_allow_html=True)

        # AI Hospital Situation Brief (one paragraph for executives)
        st.markdown("#### AI Hospital Situation Brief")
        try:
            brief = generate_situation_brief(strain)
            st.info(brief)
        except Exception:
            st.warning("AI insights temporarily unavailable.")

        # Section B: 4 KPI metrics + drill-down buttons + methodology
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total Patients", f"{total_patients:,}", delta=None, help="Click ICU Capacity tab for bed detail")
            if st.button("View Patients", key="kpi_btn_patients", use_container_width=True):
                st.session_state.page = "patients"
                st.rerun()
            with st.expander("How is this calculated?"):
                st.caption("Total Patients = census count from the patients table (current in-system).")
        with c2:
            st.metric("ICU Occupancy", f"{icu_rate:.1f}%", delta=f"{icu_occupied}/{icu_total} beds", delta_color="inverse")
            if st.button("View ICU Patients", key="kpi_btn_icu", use_container_width=True):
                st.session_state.page = "icu_patients"
                st.rerun()
            with st.expander("How is ICU occupancy calculated?"):
                st.markdown("""
                **ICU Occupancy** = ICU patients / Total ICU beds

                Example:
                - 45 occupied beds
                - 50 total beds
                - **Occupancy = 90%**

                ≥90% is critical; 70–90% is elevated.
                """)
        with c3:
            st.metric("High Readmission Risk", f"{high_readmit:,}", delta="patients ≥ 0.6 risk", delta_color="inverse", help="Patients with predicted 30-day readmission risk ≥ 60%")
            if st.button("View High Risk Patients", key="kpi_btn_readmit", use_container_width=True):
                st.session_state.page = "readmission_risk"
                st.rerun()
            with st.expander("How is readmission risk defined?"):
                st.markdown("""
                **Readmission Risk** = model-predicted probability of 30-day readmission.

                - **High risk**: score ≥ 0.6 (60%)
                - **Critical**: score ≥ 0.8 (80%)

                Based on risk_scores table (demographics, vitals, history).
                """)
        with c4:
            st.metric("Likely No-Shows", f"{likely_noshows}", delta="historical pattern", delta_color="inverse")
            if st.button("View Likely No-Shows", key="kpi_btn_noshow", use_container_width=True):
                st.session_state.page = "no_shows"
                st.rerun()
            with st.expander("How is no-show risk defined?"):
                st.markdown("""
                **No-Show Risk** = predicted likelihood of missing a scheduled appointment.

                Based on historical no-show patterns (department, reminder, distance, etc.).
                """)

        # Section C: Two columns (gauge + bed grid)
        col_left, col_right = st.columns([6, 4])
        with col_left:
            st.markdown('<div class="hd-card-title">ICU CAPACITY GAUGE</div>', unsafe_allow_html=True)
            fig, ax = plt.subplots(figsize=(6, 2))
            fig.patch.set_facecolor("#FFFFFF")
            ax.set_facecolor("#F6F8FB")
            color = "#DC2626" if icu_rate >= 80 else "#F59E0B" if icu_rate >= 60 else "#16A34A"
            ax.barh(0, icu_rate, color=color, height=0.5, zorder=3)
            ax.barh(0, 100, color="#E5E7EB", height=0.5, zorder=2)
            ax.axvline(x=80, color="#DC2626", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.axvline(x=60, color="#F59E0B", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.text(icu_rate / 2, 0, f"{icu_rate:.1f}%", ha="center", va="center", color="white", fontsize=16, fontweight="bold", zorder=4)
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            ax.set_xlabel(f"ICU Occupancy — {icu_occupied}/{icu_total} beds occupied", color="#6B7280", fontsize=10)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.tick_params(colors="#6B7280")
            fig.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        with col_right:
            st.markdown('<div class="hd-card-title">BED STATUS (occupied / free)</div>', unsafe_allow_html=True)
            beds_html = '<div class="bed-grid">'
            for i in range(min(50, icu_total)):
                cls_bed = "bed-occ" if i < icu_occupied else "bed-free"
                beds_html += f'<div class="{cls_bed}" title="Bed {i+1}"></div>'
            beds_html += "</div>"
            beds_html += '<div style="margin-top:8px; font-size:0.75rem; color:#6B7280;">● Occupied &nbsp; ● Free</div>'
            st.markdown(f'<div class="hd-card">{beds_html}</div>', unsafe_allow_html=True)

        # Section D: Three gauges
        col_g1, col_g2, col_g3 = st.columns(3)
        readmit_pct = (high_readmit / max(total_patients, 1)) * 100
        noshow_pct = min(100, (likely_noshows / max(total_patients * 0.1, 1)) * 100)
        reliability = 100 - noshow_pct

        for col, (label, val, color) in [
            (col_g1, ("ICU Capacity %", icu_rate, "#DC2626" if icu_rate >= 80 else "#F59E0B" if icu_rate >= 60 else "#16A34A")),
            (col_g2, ("Readmission Pressure %", min(100, readmit_pct), "#DC2626" if readmit_pct >= 15 else "#F59E0B" if readmit_pct >= 5 else "#16A34A")),
            (col_g3, ("Appointment Reliability %", reliability, "#DC2626" if reliability < 75 else "#F59E0B" if reliability < 90 else "#16A34A")),
        ]:
            with col:
                fig, ax = plt.subplots(figsize=(4, 1.5))
                fig.patch.set_facecolor("#FFFFFF")
                ax.set_facecolor("#F6F8FB")
                ax.barh(0, val, color=color, height=0.5, zorder=3)
                ax.barh(0, 100, color="#E5E7EB", height=0.5, zorder=2)
                ax.set_xlim(0, 100)
                ax.set_ylim(-0.5, 0.5)
                ax.set_yticks([])
                ax.set_xlabel(label, color="#6B7280", fontsize=9)
                for spine in ax.spines.values():
                    spine.set_visible(False)
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)

        # Section E: Alerts feed
        st.markdown('<div class="hd-card-title">ACTIVE ALERTS</div>', unsafe_allow_html=True)
        alerts = []
        if icu_rate >= 80:
            alerts.append(("🚨", "danger", f"ICU CRITICAL: {icu_rate:.0f}% occupancy — escalation recommended"))
        elif icu_rate >= 60:
            alerts.append(("⚠️", "warning", f"ICU ELEVATED: {icu_rate:.0f}% occupancy — monitor closely"))
        if high_readmit > 100:
            alerts.append(("⚠️", "warning", f"{high_readmit} patients flagged for high readmission risk"))
        if not alerts:
            alerts.append(("✅", "normal", "All systems operating within normal parameters"))

        color_map = {"danger": "#DC2626", "warning": "#F59E0B", "normal": "#16A34A"}
        for icon, level, msg in alerts:
            st.markdown(f"""
            <div style="border-left:3px solid {color_map[level]}; 
                        padding:10px 14px; margin:6px 0;
                        background:#FFFFFF; border:1px solid #E5E7EB; border-radius:0 6px 6px 0;
                        color:#1A1A1A; font-size:0.9rem;">
                {icon} {msg}
            </div>
            """, unsafe_allow_html=True)

        # Operational Recommendations (LLM)
        st.markdown("#### Operational Recommendations")
        try:
            recs = generate_operational_recommendations(strain)
            st.info(recs)
        except Exception:
            st.warning("AI insights temporarily unavailable.")

        # Predictive ICU forecast (next 12h, 24h, 48h)
        st.markdown("#### Projected ICU Occupancy")
        try:
            icu_trend_df = load_trend_data("icu_occupancy", days_7=True)
            proj = predict_icu_load(icu_rate, icu_trend_df, icu_total)
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric("Next 12h projection", f"{proj['next_12h']:.0f}%", help="Simple linear/rolling projection")
            fc2.metric("Next 24h projection", f"{proj['next_24h']:.0f}%", help="Based on recent trend")
            fc3.metric("Next 48h projection", f"{proj['next_48h']:.0f}%", help="Based on recent trend")
        except Exception as e:
            st.caption(f"Forecast unavailable: {e}")

    # ─── TAB 2: ICU Capacity ──────────────────────────────────────────────
    with tab2:
        try:
            trend_df = load_trend(30)
        except Exception as e:
            st.error(f"Failed to load trend: {e}")
            trend_df = pd.DataFrame()

        row1_left, row1_right = st.columns([6, 4])
        with row1_left:
            st.markdown('<div class="hd-card-title">ICU CAPACITY GAUGE</div>', unsafe_allow_html=True)
            fig, ax = plt.subplots(figsize=(8, 3))
            fig.patch.set_facecolor("#FFFFFF")
            ax.set_facecolor("#F6F8FB")
            color = "#DC2626" if icu_rate >= 80 else "#F59E0B" if icu_rate >= 60 else "#16A34A"
            ax.barh(0, icu_rate, color=color, height=0.5, zorder=3)
            ax.barh(0, 100, color="#E5E7EB", height=0.5, zorder=2)
            ax.axvline(x=80, color="#DC2626", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.axvline(x=60, color="#F59E0B", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.text(icu_rate / 2, 0, f"{icu_rate:.1f}%", ha="center", va="center", color="white", fontsize=18, fontweight="bold", zorder=4)
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            ax.set_xlabel(f"ICU Occupancy — {icu_occupied}/{icu_total} beds", color="#6B7280", fontsize=10)
            for spine in ax.spines.values():
                spine.set_visible(False)
            fig.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        with row1_right:
            beds_html = '<div class="bed-grid">'
            for i in range(min(50, icu_total)):
                cls_bed = "bed-occ" if i < icu_occupied else "bed-free"
                beds_html += f'<div class="{cls_bed}"></div>'
            beds_html += "</div>"
            st.markdown(f'<div class="hd-card">{beds_html}</div>', unsafe_allow_html=True)

            if not trend_df.empty and "admissions" in trend_df.columns:
                avg_adm = trend_df["admissions"].mean()
                peak = int(trend_df["admissions"].max())
                direction = "↑" if len(trend_df) >= 2 and trend_df["admissions"].iloc[-1] > trend_df["admissions"].iloc[0] else ("↓" if len(trend_df) >= 2 else "→")
            else:
                avg_adm, peak, direction = "—", "—", "—"
            st.metric("Avg Daily Admissions", f"{avg_adm:.1f}" if isinstance(avg_adm, (int, float)) else avg_adm)
            st.metric("Peak Occupancy", str(peak))
            st.metric("Current Trend", direction)
            st.metric("Discharge Pending", str(discharge_pending))

        # Admissions trend chart
        st.markdown('<div class="hd-card-title">30-DAY ADMISSIONS & DISCHARGES</div>', unsafe_allow_html=True)
        if trend_df.empty or "date" not in trend_df.columns:
            st.warning("No data available")
        else:
            trend_df = trend_df.copy()
            trend_df["date"] = pd.to_datetime(trend_df["date"], errors="coerce")
            trend_df = trend_df.dropna(subset=["date"])
            if trend_df.empty:
                st.warning("No data available")
            else:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=trend_df["date"], y=trend_df["admissions"],
                    name="Admissions", fill="tozeroy", fillcolor="rgba(59,130,246,0.15)",
                    line=dict(color="#3B82F6", width=2), mode="lines+markers", marker=dict(size=5),
                ))
                if "discharges" in trend_df.columns:
                    fig.add_trace(go.Scatter(
                        x=trend_df["date"], y=trend_df["discharges"],
                        name="Discharges", line=dict(color="#16A34A", width=2),
                        mode="lines+markers", marker=dict(size=5),
                    ))
                fig.add_hline(y=45, line_dash="dash", line_color="#DC2626", opacity=0.6, annotation_text="Critical (90%)")
                fig.add_hline(y=35, line_dash="dash", line_color="#F59E0B", opacity=0.6, annotation_text="Caution (70%)")
                fig.update_layout(**_plotly_layout(), height=350, title=dict(text="30-Day Admissions & Discharges", font=dict(color="#1A1A1A", size=14)))
                st.plotly_chart(fig, use_container_width=True)

    # ─── TAB 3: High Readmission Risk ─────────────────────────────────────
    with tab3:
        try:
            high_risk_df = load_readmission(limit=100)
        except Exception as e:
            st.error(f"Failed to load: {e}")
            high_risk_df = pd.DataFrame()

        if high_risk_df is None or not isinstance(high_risk_df, pd.DataFrame):
            high_risk_df = pd.DataFrame()

        cols = st.columns([2, 1, 1, 1])
        cols[0].markdown(f"**{high_readmit} patients** flagged for 30-day readmission risk ≥ 60%")
        if not high_risk_df.empty and "readmission_risk" in high_risk_df.columns:
            critical_n = len(high_risk_df[high_risk_df["readmission_risk"] >= 0.8])
            high_n = len(high_risk_df[(high_risk_df["readmission_risk"] >= 0.6) & (high_risk_df["readmission_risk"] < 0.8)])
        else:
            critical_n, high_n = 0, 0
        cols[1].metric("🔴 Critical (≥80%)", critical_n)
        cols[2].metric("🟡 High (60-80%)", high_n)

        sort_col, filter_col = st.columns([3, 3])
        sort_by = sort_col.selectbox("Sort by", ["Risk Score ↓", "Patient ID", "Admissions"])
        filter_by = filter_col.selectbox("Filter", ["All patients", "Critical only (≥80%)", "High (60-80%)"])

        filtered_df = high_risk_df.copy()
        if not filtered_df.empty and "readmission_risk" in filtered_df.columns:
            risk_min, risk_max = st.session_state.sidebar_risk_min, st.session_state.sidebar_risk_max
            filtered_df = filtered_df[(filtered_df["readmission_risk"] >= risk_min) & (filtered_df["readmission_risk"] <= risk_max)]
            if st.session_state.sidebar_readmit_dept != "All":
                dept_col = next((c for c in filtered_df.columns if "department" in c.lower() or "dept" in c.lower()), None)
                if dept_col:
                    filtered_df = filtered_df[filtered_df[dept_col].astype(str) == st.session_state.sidebar_readmit_dept]
            if filter_by == "Critical only (≥80%)":
                filtered_df = filtered_df[filtered_df["readmission_risk"] >= 0.8]
            elif filter_by == "High (60-80%)":
                filtered_df = filtered_df[(filtered_df["readmission_risk"] >= 0.6) & (filtered_df["readmission_risk"] < 0.8)]
            if sort_by == "Risk Score ↓":
                filtered_df = filtered_df.sort_values("readmission_risk", ascending=False)
            elif sort_by == "Patient ID" and "patient_id" in filtered_df.columns:
                filtered_df = filtered_df.sort_values("patient_id")
            elif sort_by == "Admissions" and "admission_count" in filtered_df.columns:
                filtered_df = filtered_df.sort_values("admission_count", ascending=False)

        if filtered_df.empty:
            st.warning("No data available")
        else:
            batch_size = 12
            rows = filtered_df.head(50)
            for start in range(0, len(rows), batch_size):
                batch = rows.iloc[start : start + batch_size]
                cards_html = '<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:12px; width:100%;">'
                for _, row in batch.iterrows():
                    risk = float(row.get("readmission_risk", 0))
                    risk_pct = risk * 100
                    bar_color = "#DC2626" if risk >= 0.8 else "#F59E0B"
                    badge_class = "risk-critical" if risk >= 0.8 else "risk-high"
                    badge_text = "CRITICAL" if risk >= 0.8 else "HIGH RISK"
                    pid = html_module.escape(str(row.get("patient_id", "—")))
                    bar_pct = min(100, risk_pct)
                    cards_html += (
                        f'<div style="background:#FFFFFF; border:1px solid #E5E7EB; border-top:3px solid {bar_color}; border-radius:10px; padding:16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); min-width:0;">'
                        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; gap:8px;">'
                        f'<span style="font-family:\'DM Mono\',monospace; font-size:0.9rem; color:#1A1A1A; overflow:hidden; text-overflow:ellipsis;">{pid}</span>'
                        f'<span class="{badge_class}" style="flex-shrink:0;">{badge_text}</span>'
                        f'</div>'
                        f'<div style="background:#F6F8FB; border-radius:4px; height:8px; margin-bottom:8px; overflow:hidden;">'
                        f'<div style="background:{bar_color}; width:{bar_pct:.0f}%; height:100%; border-radius:4px; min-width:0;"></div>'
                        f'</div>'
                        f'<div style="color:#6B7280; font-size:0.8rem;">Risk: {risk_pct:.1f}%</div>'
                        f'</div>'
                    )
                cards_html += "</div>"
                st.markdown(cards_html, unsafe_allow_html=True)

        # Root Cause Analysis: Top Drivers of Readmission Risk
        st.markdown("#### Top Drivers of Readmission Risk")
        try:
            drivers = analyze_readmission_drivers(high_risk_df)
            if drivers.get("top_conditions"):
                for item in drivers["top_conditions"][:10]:
                    st.markdown(f"- **{item['name']}** — {item['count']} patients")
                cond_df = pd.DataFrame(drivers["top_conditions"])
                st.bar_chart(cond_df.set_index("name")["count"], height=250)
            if drivers.get("departments"):
                dept_df = pd.DataFrame(drivers["departments"])
                st.bar_chart(dept_df.set_index("name")["count"], height=220)
            if drivers.get("discharge_types"):
                disc_df = pd.DataFrame(drivers["discharge_types"])
                st.bar_chart(disc_df.set_index("name")["count"], height=220)
            if not any([drivers.get("top_conditions"), drivers.get("departments"), drivers.get("discharge_types")]):
                st.caption("No driver data available (diagnosis/department/discharge columns may be missing).")
        except Exception as e:
            st.caption(f"Root cause analysis unavailable: {e}")

        # Risk distribution chart
        if not high_risk_df.empty and "readmission_risk" in high_risk_df.columns:
            bins = ["0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]
            ranges = [(0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
            counts = [len(high_risk_df[(high_risk_df["readmission_risk"] >= lo) & (high_risk_df["readmission_risk"] < hi)]) for lo, hi in ranges]
            colors = ["#FEF08A", "#FCD34D", "#F97316", "#DC2626"]
            fig = go.Figure(go.Bar(x=bins, y=counts, marker_color=colors))
            fig.update_layout(**_plotly_layout(), height=250, title="Risk Score Distribution")
            st.plotly_chart(fig, use_container_width=True)

    # ─── TAB 4: No-Show Risk ─────────────────────────────────────────────
    with tab4:
        st.markdown(f"**{likely_noshows} appointments** at risk based on historical patterns")

        try:
            dept_df = load_noshow_dept()
            noshow_df = load_noshow_patients()
        except Exception as e:
            st.error(f"Failed to load: {e}")
            dept_df = pd.DataFrame()
            noshow_df = pd.DataFrame()

        if dept_df is None or not isinstance(dept_df, pd.DataFrame):
            dept_df = pd.DataFrame()
        if noshow_df is None or not isinstance(noshow_df, pd.DataFrame):
            noshow_df = pd.DataFrame()

        col_chart, col_stats = st.columns([6, 4])
        with col_chart:
            if dept_df.empty or "no_show_rate" not in dept_df.columns:
                st.warning("No data available")
            else:
                dept_col = "department" if "department" in dept_df.columns else dept_df.columns[0]
                dept_df = dept_df.sort_values("no_show_rate", ascending=False)
                colors = ["#DC2626" if r > 0.20 else "#F59E0B" if r > 0.10 else "#16A34A" for r in dept_df["no_show_rate"]]
                fig = go.Figure(go.Bar(
                    x=dept_df["no_show_rate"] * 100,
                    y=dept_df[dept_col].astype(str).str.capitalize(),
                    orientation="h",
                    marker_color=colors,
                    text=[f"{r*100:.1f}%" for r in dept_df["no_show_rate"]],
                    textposition="outside",
                ))
                fig.add_vline(x=20, line_dash="dash", line_color="#DC2626", annotation_text="High risk 20%")
                fig.add_vline(x=10, line_dash="dash", line_color="#F59E0B", annotation_text="Moderate 10%")
                layout = _plotly_layout()
                layout["margin"] = dict(t=30, b=40, l=120, r=80)
                fig.update_layout(**layout, height=300, xaxis_title="No-Show Rate (%)")
                st.plotly_chart(fig, use_container_width=True)

        with col_stats:
            if not dept_df.empty and "no_show_rate" in dept_df.columns:
                highest_dept = dept_df.iloc[0]
                lowest_dept = dept_df.iloc[-1]
                overall_rate = dept_df["no_show_rate"].mean() * 100
                dept_col = "department" if "department" in dept_df.columns else dept_df.columns[0]
                st.metric("Highest Risk Dept", str(highest_dept.get(dept_col, "N/A")).capitalize(), f"{highest_dept['no_show_rate']*100:.1f}%")
                st.metric("Lowest Risk Dept", str(lowest_dept.get(dept_col, "N/A")).capitalize(), f"{lowest_dept['no_show_rate']*100:.1f}%")
                st.metric("Overall No-Show Rate", f"{overall_rate:.1f}%")
            else:
                st.metric("Highest Risk Dept", "N/A", "")
                st.metric("Lowest Risk Dept", "N/A", "")
                st.metric("Overall No-Show Rate", "N/A")
            st.metric("Patients at Risk", str(likely_noshows))

        st.markdown("#### Patients with Historical No-Show Pattern")
        if noshow_df.empty:
            st.warning("No data available")
        else:
            st.dataframe(noshow_df.head(50), use_container_width=True, hide_index=True)

    # ─── TAB 5: Patient Twin ──────────────────────────────────────────────
    with tab5:
        if "loaded_pid" not in st.session_state:
            st.session_state.loaded_pid = None

        col_sel, col_content = st.columns([1, 3])
        with col_sel:
            try:
                patient_ids = load_patient_ids()
            except Exception:
                patient_ids = []
            selected_pid = st.selectbox("Select Patient", [""] + list(patient_ids), format_func=lambda x: "Select patient..." if x == "" else x)
            load_btn = st.button("Load Patient Twin", type="primary", use_container_width=True)

        if load_btn and selected_pid:
            st.session_state.loaded_pid = selected_pid

        with col_content:
            if st.session_state.loaded_pid:
                try:
                    hist = get_patient_history(st.session_state.loaded_pid)
                except Exception as e:
                    st.error(f"Failed to load patient: {e}")
                    hist = {}

                dem = hist.get("demographics", {})
                if dem:
                    st.markdown("#### Demographics")
                    dem_cols = st.columns(3)
                    items = list(dem.items())
                    for i, (k, v) in enumerate(items[:9]):
                        dem_cols[i % 3].metric(k.replace("_", " ").title(), str(v))

                risk_scores = hist.get("risk_scores", pd.DataFrame())
                if risk_scores is not None and isinstance(risk_scores, pd.DataFrame) and not risk_scores.empty:
                    st.markdown("#### Risk Profile")
                    chip_html = '<div style="display:flex; gap:8px; flex-wrap:wrap; margin:8px 0;">'
                    for col in ["readmission_risk", "icu_risk", "no_show_risk"]:
                        if col in risk_scores.columns:
                            val = risk_scores[col].iloc[0]
                            color = "#DC2626" if val >= 0.8 else "#F59E0B" if val >= 0.5 else "#16A34A"
                            label = col.replace("_risk", "").replace("_", " ").title()
                            chip_html += f'<div style="background:{color}22; border:1px solid {color}; color:{color}; padding:6px 14px; border-radius:20px; font-family:monospace; font-size:0.9rem;">{label}: {val:.2f}</div>'
                    chip_html += "</div>"
                    st.markdown(chip_html, unsafe_allow_html=True)

                vitals = hist.get("vitals", pd.DataFrame())
                if vitals is not None and isinstance(vitals, pd.DataFrame) and not vitals.empty:
                    v = vitals.tail(20)
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("Heart Rate (bpm)", "SpO2 (%)"))
                    if "heart_rate" in v.columns:
                        fig.add_trace(go.Scatter(y=v["heart_rate"], mode="lines+markers", line=dict(color="#F97316", width=2), name="Heart Rate"), row=1, col=1)
                        fig.add_hline(y=100, line_dash="dash", line_color="#DC2626", opacity=0.5, row=1, col=1)
                        fig.add_hline(y=60, line_dash="dash", line_color="#DC2626", opacity=0.5, row=1, col=1)
                    if "oxygen_saturation" in v.columns:
                        fig.add_trace(go.Scatter(y=v["oxygen_saturation"], mode="lines+markers", line=dict(color="#3B82F6", width=2), name="SpO2"), row=2, col=1)
                        fig.add_hline(y=95, line_dash="dash", line_color="#DC2626", opacity=0.5, row=2, col=1)
                    layout = _plotly_layout()
                    layout["margin"] = dict(t=40, b=20, l=50, r=20)
                    fig.update_layout(**layout, height=350, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

                admissions = hist.get("admissions", pd.DataFrame())
                if admissions is not None and isinstance(admissions, pd.DataFrame) and not admissions.empty:
                    st.markdown("#### Admission History")
                    st.dataframe(admissions, use_container_width=True, hide_index=True)
            else:
                st.info("Select a patient and click Load Patient Twin")

    # ─── TAB 6: Trends ────────────────────────────────────────────────────
    with tab6:
        # Time-series trends (ICU, Readmission, No-Show)
        period = st.radio("Trend period", ["Last 7 days", "Last 30 days"], horizontal=True, key="trend_period")
        days_7 = period == "Last 7 days"
        st.markdown("#### ICU Occupancy Trend")
        try:
            icu_trend = load_trend_data("icu_occupancy", days_7=days_7)
            if not icu_trend.empty and "date" in icu_trend.columns:
                st.line_chart(icu_trend.set_index("date")[["value"]], height=250)
            else:
                st.caption("No ICU trend data available.")
        except Exception as e:
            st.error("Unable to load hospital data.")
            st.caption(str(e))
        st.markdown("#### High Readmission Risk Trend")
        try:
            readmit_trend = load_trend_data("readmission_risk", days_7=days_7)
            if not readmit_trend.empty and "date" in readmit_trend.columns:
                st.line_chart(readmit_trend.set_index("date")[["value"]], height=250)
            else:
                st.caption("No readmission trend data available.")
        except Exception as e:
            st.error("Unable to load hospital data.")
            st.caption(str(e))
        st.markdown("#### Appointment No-Show Trend")
        try:
            noshow_trend = load_trend_data("no_show", days_7=days_7)
            if not noshow_trend.empty and "date" in noshow_trend.columns:
                st.line_chart(noshow_trend.set_index("date")[["value"]], height=250)
            else:
                st.caption("No no-show trend data available.")
        except Exception as e:
            st.error("Unable to load hospital data.")
            st.caption(str(e))
        st.markdown("---")
        st.markdown("#### Admissions & Discharges (60-day)")
        try:
            trend_df = load_trend(60)
        except Exception as e:
            st.error("Unable to load hospital data.")
            trend_df = pd.DataFrame()

        c1, c2, c3 = st.columns(3)
        show_ma = c3.checkbox("Show 7-day moving average", value=True)
        metric = c2.selectbox("Metric", ["Both", "Admissions only", "Discharges only"])

        if trend_df.empty or "date" not in trend_df.columns:
            st.warning("No data available")
        else:
            trend_df = trend_df.copy()
            trend_df["date"] = pd.to_datetime(trend_df["date"], errors="coerce")
            trend_df = trend_df.dropna(subset=["date"])

            fig = go.Figure()
            if metric in ("Both", "Admissions only") and "admissions" in trend_df.columns:
                fig.add_trace(go.Scatter(x=trend_df["date"], y=trend_df["admissions"], name="Admissions", fill="tozeroy", fillcolor="rgba(59,130,246,0.15)", line=dict(color="#3B82F6", width=2), mode="lines+markers"))
            if metric in ("Both", "Discharges only") and "discharges" in trend_df.columns:
                fig.add_trace(go.Scatter(x=trend_df["date"], y=trend_df["discharges"], name="Discharges", line=dict(color="#16A34A", width=2), mode="lines+markers"))
            if show_ma and "admissions" in trend_df.columns and len(trend_df) >= 7:
                ma = trend_df["admissions"].rolling(7, min_periods=1).mean()
                fig.add_trace(go.Scatter(x=trend_df["date"], y=ma, name="7-day avg", line=dict(color="#F59E0B", width=1.5, dash="dash")))
            fig.update_layout(**_plotly_layout(), height=350, title="Admissions & Discharges")
            st.plotly_chart(fig, use_container_width=True)

            # Net flow chart
            discharges = trend_df["discharges"] if "discharges" in trend_df.columns else pd.Series(0, index=trend_df.index)
            net = trend_df["admissions"] - discharges
            colors = ["#16A34A" if n <= 0 else "#DC2626" for n in net]
            fig2 = go.Figure(go.Bar(x=trend_df["date"], y=net, marker_color=colors))
            fig2.add_hline(y=0, line_color="#E5E7EB", line_width=1)
            fig2.update_layout(**_plotly_layout(), height=250, title="Net Daily Patient Flow (Admissions − Discharges)")
            st.plotly_chart(fig2, use_container_width=True)

            # Stats row
            avg = trend_df["admissions"].mean()
            total = trend_df["admissions"].sum()
            peak_idx = trend_df["admissions"].idxmax()
            peak_day = str(trend_df.loc[peak_idx, "date"])[:10] if len(trend_df) else "N/A"
            direction = "↑ Increasing" if trend_df["admissions"].iloc[-1] > trend_df["admissions"].iloc[0] else "↓ Decreasing"
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Avg Daily Admissions", f"{avg:.1f}")
            mc2.metric("Total Admissions", f"{int(total):,}")
            mc3.metric("Peak Day", peak_day)
            mc4.metric("Trend Direction", direction)

    # ─── TAB 7: AI Assistant ───────────────────────────────────────────────
    with tab7:
        if "ai_question" not in st.session_state:
            st.session_state.ai_question = ""
        if "ai_history" not in st.session_state:
            st.session_state.ai_history = []

        q1, q2, q3, q4 = st.columns(4)
        if q1.button("🏥 Who needs attention today?"):
            st.session_state.ai_question = "Who needs attention today?"
            st.rerun()
        if q2.button("📈 ICU forecast tomorrow"):
            st.session_state.ai_question = "What is the ICU risk forecast for tomorrow?"
            st.rerun()
        if q3.button("📅 Worst no-show departments"):
            st.session_state.ai_question = "Which department has the most no-shows this week?"
            st.rerun()
        if q4.button("⚡ Summarize readmission trends"):
            st.session_state.ai_question = "Summarize readmission risk trends"
            st.rerun()

        question = st.text_area("Your question", value=st.session_state.ai_question, height=100, placeholder="Ask about patients, ICU capacity, no-shows...")
        col_ask, col_clear = st.columns([2, 1])
        ask_btn = col_ask.button("Ask AI", type="primary", use_container_width=True)
        if col_clear.button("Clear", use_container_width=True):
            st.session_state.ai_history = []
            st.session_state.ai_question = ""
            st.rerun()

        if ask_btn and question.strip():
            with st.spinner("Thinking..."):
                try:
                    answer = answer_user_question(question.strip(), strain)
                    st.session_state.ai_history.append((question.strip(), str(answer)))
                    if len(st.session_state.ai_history) > 3:
                        st.session_state.ai_history = st.session_state.ai_history[-3:]
                except Exception as e:
                    st.session_state.ai_history.append((question.strip(), f"AI unavailable: {e}"))

        for q, a in reversed(st.session_state.ai_history):
            st.markdown(f"""
            <div style="text-align:right; margin:8px 0;">
                <div style="display:inline-block; background:#3A7BD5; color:#fff; 
                            padding:10px 16px; border-radius:12px; 
                            max-width:75%; font-size:0.9rem;">{q}</div>
            </div>
            """, unsafe_allow_html=True)
            lines = [l.strip() for l in str(a).split("\n") if l.strip()]
            content = '<ul style="margin:0; padding-left:18px;">' + "".join(f'<li style="margin-bottom:4px;">{l}</li>' for l in lines) + "</ul>" if len(lines) > 1 else f'<p style="margin:0;">{a}</p>'
            st.markdown(f"""
            <div style="text-align:left; margin:8px 0;">
                <div style="display:inline-block; background:#FFFFFF; 
                            border:1px solid #E5E7EB; color:#1A1A1A;
                            padding:12px 16px; border-radius:12px;
                            max-width:85%; font-size:0.9rem;">{content}</div>
            </div>
            """, unsafe_allow_html=True)

    # Debug already in sidebar above
    if show_debug:
        with st.sidebar:
            st.json(strain)

    # ─── Footer ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f'<div style="text-align:center; color:#6B7280; font-size:0.75rem; padding:8px;">'
        f'⚠️ Demo data as of {strain.get("data_as_of", "unknown")} &nbsp;|&nbsp; '
        f"Hospital Digital Twin &nbsp;|&nbsp; "
        f'Supabase {"✓" if os.environ.get("SUPABASE_URL") else "✗"}'
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
