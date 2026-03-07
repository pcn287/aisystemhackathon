"""
Hospital Digital Twin — Streamlit Dashboard

Uses the same analytics layer (hospital_analytics.py) and Supabase backend as the
Shiny app. This file is standalone; it does not modify app.py, hospital_analytics.py,
or database_connection.py.

How to run:

    pip install streamlit plotly
    streamlit run streamlit_dashboard.py

Or from the hospital_dashboard directory:

    streamlit run streamlit_dashboard.py

Environment: Ensure .env (or environment) has SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
(or SUPABASE_KEY). Optional: OPENAI_API_KEY for AI features.
"""

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
from hospital_ai_agent import answer_user_question


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


def _plotly_layout():
    return dict(
        paper_bgcolor="#131F35",
        plot_bgcolor="#0B1120",
        font=dict(color="#F0F6FF"),
        margin=dict(t=30, b=40, l=50, r=20),
        xaxis=dict(gridcolor="#1E3A5F", showgrid=True),
        yaxis=dict(gridcolor="#1E3A5F", showgrid=True),
        legend=dict(bgcolor="#1A2942", bordercolor="#1E3A5F"),
    )


def main():
    st.set_page_config(
        page_title="Hospital Operations Command Center",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Load strain first (used in navbar and throughout)
    try:
        strain = load_strain()
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

    # ─── CSS Theme ────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
    
    .stApp { 
        background-color: #0B1120; 
        font-family: 'DM Sans', sans-serif;
        color: #F0F6FF;
    }
    
    [data-testid="stSidebar"] {
        background-color: #131F35;
        border-right: 1px solid #1E3A5F;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        background-color: #131F35;
        border-bottom: 1px solid #1E3A5F;
        padding: 0 16px;
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        color: #6B8CAE;
        font-size: 0.85rem;
        font-weight: 500;
        padding: 12px 20px;
        border-radius: 0;
        border-bottom: 2px solid transparent;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #3B82F6 !important;
        border-bottom: 2px solid #3B82F6 !important;
        background: transparent !important;
    }
    
    [data-testid="stMetric"] {
        background: #131F35;
        border: 1px solid #1E3A5F;
        border-radius: 12px;
        padding: 20px;
    }
    [data-testid="stMetricLabel"] { 
        color: #6B8CAE; 
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    [data-testid="stMetricValue"] { 
        color: #F0F6FF;
        font-family: 'DM Mono', monospace;
        font-size: 1.8rem;
    }
    
    .hd-card {
        background: #131F35;
        border: 1px solid #1E3A5F;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .hd-card-title {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #6B8CAE;
        margin-bottom: 12px;
    }
    
    .banner-normal  { background:#065F46; color:#ECFDF5; padding:16px 20px; border-radius:10px; margin-bottom:16px; }
    .banner-caution { background:#78350F; color:#FFFBEB; padding:16px 20px; border-radius:10px; margin-bottom:16px; }
    .banner-critical{ background:#7F1D1D; color:#FEF2F2; padding:16px 20px; border-radius:10px; margin-bottom:16px; animation: pulse 1.5s infinite; }
    
    .hd-table { width:100%; border-collapse:collapse; font-size:0.85rem; }
    .hd-table th { background:#1A2942; color:#6B8CAE; padding:8px 12px; text-align:left; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.05em; }
    .hd-table td { padding:8px 12px; border-bottom:1px solid #1E3A5F; color:#F0F6FF; }
    .hd-table tr:hover td { background:#1A2942; }
    
    .risk-critical { background:#7F1D1D; color:#FCA5A5; padding:3px 10px; border-radius:20px; font-size:0.75rem; font-family:'DM Mono',monospace; }
    .risk-high     { background:#78350F; color:#FCD34D; padding:3px 10px; border-radius:20px; font-size:0.75rem; font-family:'DM Mono',monospace; }
    .risk-moderate { background:#1A2942; color:#93C5FD; padding:3px 10px; border-radius:20px; font-size:0.75rem; font-family:'DM Mono',monospace; }
    
    .bed-grid { display:grid; grid-template-columns:repeat(10, 36px); gap:6px; }
    .bed-occ  { width:36px; height:36px; background:#EF4444; border-radius:6px; }
    .bed-free { width:36px; height:36px; background:#10B981; border-radius:6px; }
    
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
    .block-container { padding-top: 1rem; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.85; } }
    </style>
    """, unsafe_allow_html=True)

    # ─── Top Navbar ───────────────────────────────────────────────────────
    strain_color = "#EF4444" if strain.get("strain_level") == "critical" else "#F59E0B" if strain.get("strain_level") == "elevated" else "#10B981"
    st.markdown(f"""
    <div style="display:flex; align-items:center; justify-content:space-between;
                padding:16px 24px; background:#131F35; 
                border-bottom:1px solid #1E3A5F; margin-bottom:24px;">
        <div style="display:flex; align-items:center; gap:12px;">
            <span style="font-size:1.5rem;">🏥</span>
            <span style="font-weight:700; font-size:1.1rem; color:#F0F6FF;">
                Hospital Operations Command Center
            </span>
        </div>
        <div style="color:#6B8CAE; font-size:0.8rem;">
            Data as of: {strain.get('data_as_of', 'unknown')} &nbsp;|&nbsp; 
            Strain: <span style="color:{strain_color};">{str(strain.get('strain_level', 'unknown')).upper()}</span>
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

    # ─── Tabs ─────────────────────────────────────────────────────────────
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

        # Section B: 4 KPI metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total Patients", f"{total_patients:,}", delta=None, help="Click ICU Capacity tab for bed detail")
        with c2:
            st.metric("ICU Occupancy", f"{icu_rate:.1f}%", delta=f"{icu_occupied}/{icu_total} beds", delta_color="inverse")
        with c3:
            st.metric("High Readmission Risk", f"{high_readmit:,}", delta="patients ≥ 0.6 risk", delta_color="inverse", help="Patients with predicted 30-day readmission risk ≥ 60%")
        with c4:
            st.metric("Likely No-Shows", f"{likely_noshows}", delta="historical pattern", delta_color="inverse")

        # Section C: Two columns (gauge + bed grid)
        col_left, col_right = st.columns([6, 4])
        with col_left:
            st.markdown('<div class="hd-card-title">ICU CAPACITY GAUGE</div>', unsafe_allow_html=True)
            fig, ax = plt.subplots(figsize=(6, 2))
            fig.patch.set_facecolor("#131F35")
            ax.set_facecolor("#131F35")
            color = "#EF4444" if icu_rate >= 90 else "#F59E0B" if icu_rate >= 70 else "#10B981"
            ax.barh(0, icu_rate, color=color, height=0.5, zorder=3)
            ax.barh(0, 100, color="#1E3A5F", height=0.5, zorder=2)
            ax.axvline(x=90, color="#EF4444", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.axvline(x=70, color="#F59E0B", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.text(icu_rate / 2, 0, f"{icu_rate:.1f}%", ha="center", va="center", color="white", fontsize=16, fontweight="bold", zorder=4)
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            ax.set_xlabel(f"ICU Occupancy — {icu_occupied}/{icu_total} beds occupied", color="#6B8CAE", fontsize=10)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.tick_params(colors="#6B8CAE")
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
            beds_html += '<div style="margin-top:8px; font-size:0.75rem; color:#6B8CAE;">● Occupied &nbsp; ● Free</div>'
            st.markdown(f'<div class="hd-card">{beds_html}</div>', unsafe_allow_html=True)

        # Section D: Three gauges
        col_g1, col_g2, col_g3 = st.columns(3)
        readmit_pct = (high_readmit / max(total_patients, 1)) * 100
        noshow_pct = min(100, (likely_noshows / max(total_patients * 0.1, 1)) * 100)
        reliability = 100 - noshow_pct

        for col, (label, val, color) in [
            (col_g1, ("ICU Capacity %", icu_rate, "#EF4444" if icu_rate >= 90 else "#F59E0B" if icu_rate >= 70 else "#10B981")),
            (col_g2, ("Readmission Pressure %", min(100, readmit_pct), "#EF4444" if readmit_pct >= 15 else "#F59E0B" if readmit_pct >= 5 else "#10B981")),
            (col_g3, ("Appointment Reliability %", reliability, "#EF4444" if reliability < 75 else "#F59E0B" if reliability < 90 else "#10B981")),
        ]:
            with col:
                fig, ax = plt.subplots(figsize=(4, 1.5))
                fig.patch.set_facecolor("#131F35")
                ax.set_facecolor("#131F35")
                ax.barh(0, val, color=color, height=0.5, zorder=3)
                ax.barh(0, 100, color="#1E3A5F", height=0.5, zorder=2)
                ax.set_xlim(0, 100)
                ax.set_ylim(-0.5, 0.5)
                ax.set_yticks([])
                ax.set_xlabel(label, color="#6B8CAE", fontsize=9)
                for spine in ax.spines.values():
                    spine.set_visible(False)
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)

        # Section E: Alerts feed
        st.markdown('<div class="hd-card-title">ACTIVE ALERTS</div>', unsafe_allow_html=True)
        alerts = []
        if icu_rate >= 90:
            alerts.append(("🚨", "danger", f"ICU CRITICAL: {icu_rate:.0f}% occupancy — escalation recommended"))
        elif icu_rate >= 70:
            alerts.append(("⚠️", "warning", f"ICU ELEVATED: {icu_rate:.0f}% occupancy — monitor closely"))
        if high_readmit > 100:
            alerts.append(("⚠️", "warning", f"{high_readmit} patients flagged for high readmission risk"))
        if not alerts:
            alerts.append(("✅", "normal", "All systems operating within normal parameters"))

        color_map = {"danger": "#EF4444", "warning": "#F59E0B", "normal": "#10B981"}
        for icon, level, msg in alerts:
            st.markdown(f"""
            <div style="border-left:3px solid {color_map[level]}; 
                        padding:10px 14px; margin:6px 0;
                        background:#1A2942; border-radius:0 6px 6px 0;
                        color:#F0F6FF; font-size:0.9rem;">
                {icon} {msg}
            </div>
            """, unsafe_allow_html=True)

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
            fig.patch.set_facecolor("#131F35")
            ax.set_facecolor("#131F35")
            color = "#EF4444" if icu_rate >= 90 else "#F59E0B" if icu_rate >= 70 else "#10B981"
            ax.barh(0, icu_rate, color=color, height=0.5, zorder=3)
            ax.barh(0, 100, color="#1E3A5F", height=0.5, zorder=2)
            ax.axvline(x=90, color="#EF4444", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.axvline(x=70, color="#F59E0B", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.text(icu_rate / 2, 0, f"{icu_rate:.1f}%", ha="center", va="center", color="white", fontsize=18, fontweight="bold", zorder=4)
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            ax.set_xlabel(f"ICU Occupancy — {icu_occupied}/{icu_total} beds", color="#6B8CAE", fontsize=10)
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
                        name="Discharges", line=dict(color="#10B981", width=2),
                        mode="lines+markers", marker=dict(size=5),
                    ))
                fig.add_hline(y=45, line_dash="dash", line_color="#EF4444", opacity=0.6, annotation_text="Critical (90%)")
                fig.add_hline(y=35, line_dash="dash", line_color="#F59E0B", opacity=0.6, annotation_text="Caution (70%)")
                fig.update_layout(**_plotly_layout(), height=350, title=dict(text="30-Day Admissions & Discharges", font=dict(color="#F0F6FF", size=14)))
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
            cards_html = '<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px,1fr)); gap:12px;">'
            for _, row in filtered_df.head(50).iterrows():
                risk = float(row.get("readmission_risk", 0))
                risk_pct = risk * 100
                bar_color = "#EF4444" if risk >= 0.8 else "#F59E0B"
                badge_class = "risk-critical" if risk >= 0.8 else "risk-high"
                badge_text = "CRITICAL" if risk >= 0.8 else "HIGH RISK"
                pid = row.get("patient_id", "—")
                cards_html += f"""
                <div style="background:#131F35; border:1px solid #1E3A5F; 
                            border-top:3px solid {bar_color}; border-radius:10px; 
                            padding:16px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <span style="font-family:'DM Mono',monospace; font-size:0.9rem; color:#F0F6FF;">{pid}</span>
                        <span class="{badge_class}">{badge_text}</span>
                    </div>
                    <div style="background:#0B1120; border-radius:4px; height:8px; margin-bottom:8px;">
                        <div style="background:{bar_color}; width:{min(100, risk_pct):.0f}%; height:8px; border-radius:4px;"></div>
                    </div>
                    <div style="color:#6B8CAE; font-size:0.8rem;">Risk: {risk_pct:.1f}%</div>
                </div>
                """
            cards_html += "</div>"
            st.markdown(cards_html, unsafe_allow_html=True)

        # Risk distribution chart
        if not high_risk_df.empty and "readmission_risk" in high_risk_df.columns:
            bins = ["0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]
            ranges = [(0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
            counts = [len(high_risk_df[(high_risk_df["readmission_risk"] >= lo) & (high_risk_df["readmission_risk"] < hi)]) for lo, hi in ranges]
            colors = ["#FEF08A", "#FCD34D", "#F97316", "#EF4444"]
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
                colors = ["#EF4444" if r > 0.20 else "#F59E0B" if r > 0.10 else "#10B981" for r in dept_df["no_show_rate"]]
                fig = go.Figure(go.Bar(
                    x=dept_df["no_show_rate"] * 100,
                    y=dept_df[dept_col].astype(str).str.capitalize(),
                    orientation="h",
                    marker_color=colors,
                    text=[f"{r*100:.1f}%" for r in dept_df["no_show_rate"]],
                    textposition="outside",
                ))
                fig.add_vline(x=20, line_dash="dash", line_color="#EF4444", annotation_text="High risk 20%")
                fig.add_vline(x=10, line_dash="dash", line_color="#F59E0B", annotation_text="Moderate 10%")
                fig.update_layout(**_plotly_layout(), height=300, margin=dict(l=120, r=80), xaxis_title="No-Show Rate (%)")
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
                            color = "#EF4444" if val >= 0.8 else "#F59E0B" if val >= 0.5 else "#10B981"
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
                        fig.add_hline(y=100, line_dash="dash", line_color="#EF4444", opacity=0.5, row=1, col=1)
                        fig.add_hline(y=60, line_dash="dash", line_color="#EF4444", opacity=0.5, row=1, col=1)
                    if "oxygen_saturation" in v.columns:
                        fig.add_trace(go.Scatter(y=v["oxygen_saturation"], mode="lines+markers", line=dict(color="#3B82F6", width=2), name="SpO2"), row=2, col=1)
                        fig.add_hline(y=95, line_dash="dash", line_color="#EF4444", opacity=0.5, row=2, col=1)
                    fig.update_layout(**_plotly_layout(), height=350, margin=dict(t=40, b=20), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

                admissions = hist.get("admissions", pd.DataFrame())
                if admissions is not None and isinstance(admissions, pd.DataFrame) and not admissions.empty:
                    st.markdown("#### Admission History")
                    st.dataframe(admissions, use_container_width=True, hide_index=True)
            else:
                st.info("Select a patient and click Load Patient Twin")

    # ─── TAB 6: Trends ────────────────────────────────────────────────────
    with tab6:
        try:
            trend_df = load_trend(60)
        except Exception as e:
            st.error(f"Failed to load: {e}")
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
                fig.add_trace(go.Scatter(x=trend_df["date"], y=trend_df["discharges"], name="Discharges", line=dict(color="#10B981", width=2), mode="lines+markers"))
            if show_ma and "admissions" in trend_df.columns and len(trend_df) >= 7:
                ma = trend_df["admissions"].rolling(7, min_periods=1).mean()
                fig.add_trace(go.Scatter(x=trend_df["date"], y=ma, name="7-day avg", line=dict(color="#F59E0B", width=1.5, dash="dash")))
            fig.update_layout(**_plotly_layout(), height=350, title="Admissions & Discharges")
            st.plotly_chart(fig, use_container_width=True)

            # Net flow chart
            discharges = trend_df["discharges"] if "discharges" in trend_df.columns else pd.Series(0, index=trend_df.index)
            net = trend_df["admissions"] - discharges
            colors = ["#10B981" if n <= 0 else "#EF4444" for n in net]
            fig2 = go.Figure(go.Bar(x=trend_df["date"], y=net, marker_color=colors))
            fig2.add_hline(y=0, line_color="#6B8CAE", line_width=1)
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
                <div style="display:inline-block; background:#1D4ED8; color:#fff; 
                            padding:10px 16px; border-radius:12px; 
                            max-width:75%; font-size:0.9rem;">{q}</div>
            </div>
            """, unsafe_allow_html=True)
            lines = [l.strip() for l in str(a).split("\n") if l.strip()]
            content = '<ul style="margin:0; padding-left:18px;">' + "".join(f'<li style="margin-bottom:4px;">{l}</li>' for l in lines) + "</ul>" if len(lines) > 1 else f'<p style="margin:0;">{a}</p>'
            st.markdown(f"""
            <div style="text-align:left; margin:8px 0;">
                <div style="display:inline-block; background:#1A2942; 
                            border:1px solid #1E3A5F; color:#F0F6FF;
                            padding:12px 16px; border-radius:12px;
                            max-width:85%; font-size:0.9rem;">{content}</div>
            </div>
            """, unsafe_allow_html=True)

    # ─── Sidebar (optional debug) ──────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Debug")
        show_debug = st.checkbox("Show raw data", False)
        if show_debug:
            st.json(strain)

    # ─── Footer ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f'<div style="text-align:center; color:#6B8CAE; font-size:0.75rem; padding:8px;">'
        f'⚠️ Demo data as of {strain.get("data_as_of", "unknown")} &nbsp;|&nbsp; '
        f"Hospital Digital Twin &nbsp;|&nbsp; "
        f'Supabase {"✓" if os.environ.get("SUPABASE_URL") else "✗"}'
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
