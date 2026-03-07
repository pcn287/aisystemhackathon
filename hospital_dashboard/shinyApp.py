"""
Hospital Operations Command Center — Shiny for Python

Converted from streamlit_dashboard.py. Same analytics layer (hospital_analytics.py)
and Supabase backend. Light clinical dashboard theme.

Run: shiny run shinyApp.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv
_app_dir = Path(__file__).resolve().parent
for env_path in [Path.cwd() / ".env", _app_dir / ".env", _app_dir.parent / ".env"]:
    if env_path.exists():
        load_dotenv(env_path)
        break
load_dotenv()

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from shiny import App, reactive, render, ui

from hospital_analytics import (
    get_system_strain,
    get_high_readmission_patients,
    get_likely_no_shows,
    get_admissions_trend,
    get_department_no_show_rates,
    get_patient_id_list,
    get_patient_history,
    get_icu_patients,
    get_patient_list_for_dashboard,
)
from hospital_ai_agent import answer_user_question, explain_patient_risk


def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


# ─── Theme ────────────────────────────────────────────────────────────────
# Clean light clinical: #F4F7FB background, #FFFFFF cards, #3B82F6 primary accent
STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
  --bg: #F4F7FB;
  --surface: #FFFFFF;
  --border: #E2E8F0;
  --primary: #3B82F6;
  --success: #16a34a;
  --warning: #ea580c;
  --danger: #dc2626;
  --text: #1e293b;
  --muted: #64748b;
  --title-size: 22px;
  --card-heading-size: 15px;
  --metric-size: 36px;
}
* { box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg);
  color: var(--text);
  margin: 0;
  padding: 0;
  line-height: 1.5;
}
.page-title { font-size: var(--title-size); font-weight: 700; margin-bottom: 4px; }
.tab-desc { font-size: 13px; color: var(--muted); margin-bottom: 24px; line-height: 1.5; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  transition: box-shadow 0.2s;
}
.card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.card-title { font-size: var(--card-heading-size); font-weight: 600; color: var(--muted); margin-bottom: 16px; letter-spacing: 0.02em; }
.kpi-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 130px;
}
.kpi-icon { font-size: 32px; margin-bottom: 4px; color: var(--primary); }
.kpi-label { font-size: 12px; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; }
.kpi-value { font-size: var(--metric-size); font-weight: 700; line-height: 1.2; color: var(--text); }
.kpi-delta { font-size: 12px; color: var(--muted); }
.kpi-drill { margin-top: 12px; }
.kpi-drill .btn { font-size: 12px; padding: 6px 12px; }
.banner-normal { background: #dcfce7; color: #166534; border: 1px solid #86efac; padding: 20px 24px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.banner-caution { background: #ffedd5; color: #9a3412; border: 1px solid #fdba74; padding: 20px 24px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.banner-critical { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; padding: 20px 24px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.ai-insight { background: var(--surface); border-left: 4px solid var(--primary); padding: 16px 20px; border-radius: 0 10px 10px 0; margin-bottom: 24px; font-size: 14px; color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.bed-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(36px, 1fr)); gap: 8px; max-width: 100%; }
.bed-occ { width: 36px; height: 36px; background: var(--danger); border-radius: 8px; }
.bed-free { width: 36px; height: 36px; background: var(--success); border-radius: 8px; }
.bed-legend { font-size: 12px; color: var(--muted); margin-top: 12px; display: flex; gap: 16px; align-items: center; }
.bed-legend span { display: flex; align-items: center; gap: 6px; }
.bed-legend .dot-occ { width: 12px; height: 12px; background: var(--danger); border-radius: 4px; }
.bed-legend .dot-free { width: 12px; height: 12px; background: var(--success); border-radius: 4px; }
.bslib-nav-content { padding: 28px; }
.app-header { background: #3B82F6; color: #fff; padding: 16px 28px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 2px 8px rgba(59,130,246,0.3); }
.app-header-title { font-size: 1.25rem; font-weight: 700; }
.app-header-meta { font-size: 0.875rem; opacity: 0.95; }
.app-header-meta .strain-elevated { color: #fbbf24; font-weight: 600; }
.app-header-meta .strain-critical { color: #fca5a5; font-weight: 600; }
.app-header-meta .strain-normal { color: #86efac; font-weight: 600; }
.nav-card-wrapper { margin-top: 20px; }
.nav-card-wrapper .bslib-card { border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.nav-card .card-body { padding: 0; }
.navbar, nav.bslib-nav { background: var(--surface) !important; border-bottom: 1px solid var(--border); }
.navbar .nav-link, .bslib-nav .nav-link { color: var(--muted) !important; }
.navbar .nav-link:hover, .bslib-nav .nav-link:hover { color: var(--primary) !important; }
.navbar .nav-link.active, .bslib-nav .nav-link.active { color: var(--primary) !important; font-weight: 600; border-bottom: 2px solid var(--primary); }
.navbar .navbar-brand, .navbar .navbar-brand *, .bslib-nav .navbar-brand { color: var(--text) !important; }
.btn-primary { background: var(--primary) !important; border-color: var(--primary) !important; }
.bslib-sidebar { background: var(--surface) !important; border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
@media (max-width: 768px) {
  .kpi-value { font-size: 28px; }
  .kpi-card { padding: 16px; min-height: 110px; }
}
"""


_CHART_BG = "#ffffff"
_CHART_MUTED = "#6b7280"
_CHART_GRID = "#E2E8F0"

def _gauge_fig(value: float, label: str, color: str, height: float = 1.5):
    fig, ax = plt.subplots(figsize=(6, height))
    fig.patch.set_facecolor(_CHART_BG)
    ax.set_facecolor(_CHART_BG)
    ax.barh(0, value, color=color, height=0.5, zorder=3)
    ax.barh(0, 100, color=_CHART_GRID, height=0.5, zorder=2)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_xlabel(label, color=_CHART_MUTED, fontsize=9)
    ax.grid(axis="x", color=_CHART_GRID, linestyle="-", alpha=0.5, linewidth=0.5)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=_CHART_MUTED)
    fig.tight_layout()
    return fig


KPI_METHODOLOGY = {
    "total_patients": "Total Patients = distinct count of patient_id in the patients table. Includes all registered patients in the system.",
    "icu": """ICU Occupancy = ICU Patients / Total ICU Beds

Example:
45 occupied beds
50 total beds
Occupancy = 90%

High operational risk when occupancy ≥ 90%.""",
    "readmission": """Readmission Risk = patients with 30-day readmission probability ≥ 60% (0.6)

Risk scores come from the risk_scores table. Patients flagged for discharge planning and care coordination.""",
    "noshow": """No-Show Risk = appointments with high likelihood of patient no-show based on historical patterns.

Uses no_show_risk from risk_scores and past appointment outcomes. Target outreach for high-risk appointments.""",
}


TAB_DESCRIPTIONS = {
    "command": "Overview of system strain, ICU capacity, readmission pressure, and appointment reliability. Use this as your operational dashboard.",
    "icu": "Monitor ICU capacity and bed occupancy. Track admissions and discharges trends to predict when capacity may be reached.",
    "readmission": "Identify patients at high risk of 30-day readmission. Prioritize discharge planning and care coordination for these patients.",
    "noshow": "Assess appointment no-show risk by department and patient. Target outreach and reminders for high-risk appointments.",
    "twin": "Digital twin simulation: view a patient's demographics, risk profile, vitals, and admission history in one place.",
    "trends": "Operational trends over time. Analyze admissions, discharges, and net patient flow to spot patterns.",
    "ai": "AI assistant for natural language questions about patients, ICU capacity, no-shows, and readmission trends.",
    "patients": "Browse all patients with search and filters. Drill down from KPI cards to view specific patient lists.",
}


def _tab_patients():
    """All Patients drill-down: search, filters, patient list, link to Patient Twin."""
    return ui.TagList(
        ui.tags.p(TAB_DESCRIPTIONS["patients"], class_="tab-desc"),
        ui.layout_sidebar(
            ui.sidebar(
                ui.input_text("patient_search", "Search patient ID", placeholder="Filter by ID..."),
                ui.input_slider("patient_age_min", "Age min", 0, 100, 0),
                ui.input_slider("patient_age_max", "Age max", 0, 100, 100),
                ui.input_checkbox("patient_icu_only", "ICU patients only", value=False),
                ui.input_checkbox("patient_high_risk_only", "High readmission risk only (≥0.6)", value=False),
                ui.input_select("patient_list_mode", "List view", {"all": "All Patients", "icu": "ICU Patients", "readmit": "High Readmission Risk", "noshow": "Likely No-Shows"}),
                title="Filters",
            ),
            ui.TagList(
                ui.output_ui("patient_list_header"),
                ui.output_data_frame("patient_list_df"),
                ui.tags.p("Select a patient and use the Patient Twin tab for detailed view.", class_="tab-desc"),
            ),
        ),
    )


def _tab_command_center():
    return ui.TagList(
        ui.tags.p(TAB_DESCRIPTIONS["command"], class_="tab-desc"),
        ui.output_ui("health_banner"),
        ui.output_ui("ai_insight"),
        ui.layout_columns(
            ui.TagList(
                ui.output_ui("kpi_total"),
                ui.accordion(ui.accordion_panel("How is this calculated?", ui.tags.p(KPI_METHODOLOGY["total_patients"])), open=False),
            ),
            ui.TagList(
                ui.output_ui("kpi_icu"),
                ui.accordion(ui.accordion_panel("How is ICU occupancy calculated?", ui.tags.pre(KPI_METHODOLOGY["icu"], style="white-space:pre-wrap; font-size:13px;")), open=False),
            ),
            ui.TagList(
                ui.output_ui("kpi_readmit"),
                ui.accordion(ui.accordion_panel("How is readmission risk defined?", ui.tags.p(KPI_METHODOLOGY["readmission"])), open=False),
            ),
            ui.TagList(
                ui.output_ui("kpi_noshow"),
                ui.accordion(ui.accordion_panel("How is no-show risk defined?", ui.tags.p(KPI_METHODOLOGY["noshow"])), open=False),
            ),
            col_widths=(3, 3, 3, 3),
            gap="20px",
        ),
        ui.layout_columns(
            ui.output_plot("gauge_icu_main"),
            ui.output_ui("bed_grid_main"),
            col_widths=(6, 4),
        ),
        ui.layout_columns(
            ui.output_plot("gauge_icu_small"),
            ui.output_plot("gauge_readmit_small"),
            ui.output_plot("gauge_noshow_small"),
            col_widths=(4, 4, 4),
        ),
        ui.output_ui("alerts_feed"),
    )


def _tab_icu():
    return ui.TagList(
        ui.tags.p(TAB_DESCRIPTIONS["icu"], class_="tab-desc"),
        ui.layout_sidebar(
        ui.sidebar(
            ui.input_slider("icu_days", "Trend days", 7, 60, 30),
            title="Options",
        ),
        ui.layout_columns(
            ui.output_plot("gauge_icu_tab"),
            ui.output_ui("bed_grid_icu"),
            col_widths=(6, 4),
        ),
        ui.output_plot("icu_trend_plot"),
    ),
    )


def _tab_readmission():
    return ui.TagList(
        ui.tags.p(TAB_DESCRIPTIONS["readmission"], class_="tab-desc"),
        ui.output_ui("readmit_summary"),
        ui.layout_columns(
            ui.input_select("readmit_sort", "Sort by", {"risk": "Risk Score ↓", "id": "Patient ID", "admissions": "Admissions"}),
            ui.input_select("readmit_filter", "Filter", {"all": "All", "critical": "Critical (≥80%)", "high": "High (60-80%)"}),
            col_widths=(4, 4),
        ),
        ui.output_ui("readmit_cards"),
        ui.output_plot("readmit_dist_plot"),
    )


def _tab_noshow():
    return ui.TagList(
        ui.tags.p(TAB_DESCRIPTIONS["noshow"], class_="tab-desc"),
        ui.output_ui("noshow_summary"),
        ui.layout_columns(
            ui.output_plot("noshow_bar_plot"),
            ui.output_ui("noshow_stats"),
            col_widths=(6, 4),
        ),
        ui.tags.h4("Patients with Historical No-Show Pattern"),
        ui.output_data_frame("noshow_df"),
    )


def _tab_patient_twin():
    return ui.TagList(
        ui.tags.p(TAB_DESCRIPTIONS["twin"], class_="tab-desc"),
        ui.layout_sidebar(
        ui.sidebar(
            ui.input_select("twin_patient", "Patient", choices={"": "Select..."}, selected=""),
            ui.input_action_button("twin_load", "Load Patient Twin", class_="btn-primary"),
            title="Patient",
        ),
        ui.output_ui("twin_content"),
    ),
    )


def _tab_trends():
    return ui.TagList(
        ui.tags.p(TAB_DESCRIPTIONS["trends"], class_="tab-desc"),
        ui.layout_columns(
            ui.input_slider("trend_days", "Days", 7, 90, 60),
            ui.input_select("trend_metric", "Metric", {"both": "Both", "admissions": "Admissions only", "discharges": "Discharges only"}),
            ui.input_checkbox("trend_ma", "Show 7-day moving average", value=True),
            col_widths=(4, 4, 4),
        ),
        ui.output_plot("trend_main_plot"),
        ui.output_plot("trend_net_plot"),
        ui.output_ui("trend_stats"),
    )


def _tab_ai():
    return ui.TagList(
        ui.tags.p(TAB_DESCRIPTIONS["ai"], class_="tab-desc"),
        ui.layout_columns(
            ui.input_action_button("ai_q1", "🏥 Who needs attention today?"),
            ui.input_action_button("ai_q2", "📈 ICU forecast tomorrow"),
            ui.input_action_button("ai_q3", "📅 Worst no-show departments"),
            ui.input_action_button("ai_q4", "⚡ Summarize readmission trends"),
            col_widths=(3, 3, 3, 3),
        ),
        ui.input_text_area("ai_question", "Your question", placeholder="Ask about patients, ICU capacity, no-shows...", rows=3),
        ui.input_action_button("ai_ask", "Ask AI", class_="btn-primary"),
        ui.output_ui("ai_answer"),
    )


# ─── UI ───────────────────────────────────────────────────────────────────
app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.title("Hospital Operations Command Center"),
        ui.tags.style(STYLE),
        ui.tags.link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css"),
    ),
    ui.tags.div(
        ui.tags.span("🏥 Hospital Operations Command Center", class_="app-header-title"),
        ui.output_ui("header_meta"),
        class_="app-header",
    ),
    ui.tags.div(
        ui.navset_card_tab(
            ui.nav_panel("Command Center", _tab_command_center(), value="command"),
            ui.nav_panel("Patients", _tab_patients(), value="patients"),
            ui.nav_panel("ICU Capacity", _tab_icu(), value="icu"),
            ui.nav_panel("Readmission Risk", _tab_readmission(), value="readmission"),
            ui.nav_panel("No-Show Risk", _tab_noshow(), value="noshow"),
            ui.nav_panel("Patient Twin", _tab_patient_twin(), value="twin"),
            ui.nav_panel("Trends", _tab_trends(), value="trends"),
            ui.nav_panel("AI Assistant", _tab_ai(), value="ai"),
            id="main_nav",
        ),
        class_="nav-card-wrapper",
    ),
)


# ─── Server ───────────────────────────────────────────────────────────────
def server(input, output, session):
    strain = reactive.Value(None)
    loaded_pid = reactive.Value(None)
    ai_history = reactive.Value([])

    @reactive.effect
    def _load_strain():
        s = safe(get_system_strain, {})
        strain.set(s if s else {})

    @render.ui
    def header_meta():
        s = strain()
        data_as_of = s.get("data_as_of", "—") if s else "—"
        level = (s.get("strain_level") or "normal") if s else "normal"
        strain_label = level.upper()
        cls = "strain-normal" if level == "normal" else "strain-elevated" if level == "elevated" else "strain-critical"
        return ui.tags.span(
            f"Data as of: {data_as_of} | Strain: ",
            ui.tags.span(strain_label, class_=cls),
            class_="app-header-meta",
        )

    @reactive.effect
    @reactive.event(input.drill_total)
    def _drill_total():
        ui.update_navset("main_nav", selected="patients", session=session)
        try:
            ui.update_select("patient_list_mode", selected="all", session=session)
        except Exception:
            pass

    @reactive.effect
    @reactive.event(input.drill_icu)
    def _drill_icu():
        ui.update_navset("main_nav", selected="patients", session=session)
        try:
            ui.update_select("patient_list_mode", selected="icu", session=session)
            ui.update_checkbox("patient_icu_only", value=True, session=session)
        except Exception:
            pass

    @reactive.effect
    @reactive.event(input.drill_readmit)
    def _drill_readmit():
        ui.update_navset("main_nav", selected="patients", session=session)
        try:
            ui.update_select("patient_list_mode", selected="readmit", session=session)
            ui.update_checkbox("patient_high_risk_only", value=True, session=session)
        except Exception:
            pass

    @reactive.effect
    @reactive.event(input.drill_noshow)
    def _drill_noshow():
        ui.update_navset("main_nav", selected="patients", session=session)
        try:
            ui.update_select("patient_list_mode", selected="noshow", session=session)
        except Exception:
            pass

    @reactive.effect
    def _init_patient_choices():
        ids = safe(lambda: get_patient_id_list(), [])
        choices = {"": "Select patient..."}
        if ids:
            choices.update({i: i for i in ids[:500]})
        ui.update_select("twin_patient", choices=choices, session=session)

    @reactive.effect
    @reactive.event(input.twin_load)
    def _on_load_twin():
        pid = input.twin_patient()
        if pid:
            loaded_pid.set(pid)

    @reactive.effect
    @reactive.event(input.ai_q1)
    def _(): ui.update_text_area("ai_question", value="Who needs attention today?", session=session)

    @reactive.effect
    @reactive.event(input.ai_q2)
    def _(): ui.update_text_area("ai_question", value="What is the ICU risk forecast for tomorrow?", session=session)

    @reactive.effect
    @reactive.event(input.ai_q3)
    def _(): ui.update_text_area("ai_question", value="Which department has the most no-shows this week?", session=session)

    @reactive.effect
    @reactive.event(input.ai_q4)
    def _(): ui.update_text_area("ai_question", value="Summarize readmission risk trends", session=session)

    # ─── Command Center ────────────────────────────────────────────────────
    @render.ui
    def health_banner():
        s = strain()
        if not s:
            return ui.tags.div()
        score = s.get("strain_score", 0)
        if score < 40:
            cls, msg = "banner-normal", "✅ SYSTEM OPERATING NORMALLY"
        elif score <= 70:
            cls, msg = "banner-caution", "⚠️ ELEVATED STRAIN — MONITOR CLOSELY"
        else:
            cls, msg = "banner-critical", "🚨 HIGH STRAIN — ACTION REQUIRED"
        icu = (s.get("icu_rate") or 0) * 100
        readmit = (s.get("readmit_rate") or 0) * 100
        noshow = (s.get("noshow_rate") or 0) * 100
        return ui.tags.div(
            ui.tags.div(msg, style="font-weight:700; font-size:1.1rem;"),
            ui.tags.div(
                f"Strain Score: {score:.0f}/100 | ICU: {icu:.0f}% | Readmit: {readmit:.1f}% | No-Show: {noshow:.1f}%",
                style="margin-top:8px; font-size:0.85rem;",
            ),
            class_=cls,
        )

    def _metric_card(icon_class: str, label: str, value, delta=None, drill_btn=None):
        children = [
            ui.tags.div(ui.HTML(f'<i class="bi {icon_class} kpi-icon"></i>')),
            ui.tags.div(label, class_="kpi-label"),
            ui.tags.div(str(value), class_="kpi-value"),
        ]
        if delta:
            children.append(ui.tags.div(delta, class_="kpi-delta"))
        if drill_btn:
            children.append(ui.tags.div(drill_btn, class_="kpi-drill"))
        return ui.tags.div(*children, class_="kpi-card")

    @render.ui
    def kpi_total():
        s = strain()
        n = s.get("total_patients", 0) if s else 0
        btn = ui.input_action_button("drill_total", "View Patients", class_="btn btn-sm btn-outline-primary")
        return _metric_card("bi-people-fill", "Total Patients", f"{n:,}", drill_btn=btn)

    @render.ui
    def kpi_icu():
        s = strain()
        btn = ui.input_action_button("drill_icu", "View ICU Patients", class_="btn btn-sm btn-outline-primary")
        if not s:
            return _metric_card("bi-hospital", "ICU Occupancy", "—", drill_btn=btn)
        occ, tot = s.get("icu_occupied", 0), s.get("icu_total", 50)
        pct = (s.get("icu_rate") or 0) * 100
        return _metric_card("bi-hospital", "ICU Occupancy", f"{pct:.1f}%", f"{occ}/{tot} beds", drill_btn=btn)

    @render.ui
    def kpi_readmit():
        s = strain()
        n = s.get("high_readmission_count", 0) if s else 0
        btn = ui.input_action_button("drill_readmit", "View High Risk Patients", class_="btn btn-sm btn-outline-primary")
        return _metric_card("bi-arrow-repeat", "High Readmission Risk", f"{n:,}", "patients ≥ 0.6 risk", drill_btn=btn)

    @render.ui
    def kpi_noshow():
        s = strain()
        n = s.get("likely_no_show_count", 0) if s else 0
        btn = ui.input_action_button("drill_noshow", "View Likely No-Shows", class_="btn btn-sm btn-outline-primary")
        return _metric_card("bi-calendar-x", "Likely No-Shows", n, "historical pattern", drill_btn=btn)

    @render.ui
    def ai_insight():
        s = strain()
        if not s:
            return ui.tags.div()
        try:
            insight = answer_user_question("Summarize the current hospital operational situation in one sentence for stakeholders.", s)
            insight = str(insight).strip()
            if len(insight) > 200:
                insight = insight[:197] + "..."
        except Exception:
            insight = "Operational metrics are loading. Check the KPIs above for current status."
        return ui.tags.div(
            ui.tags.span("💡 ", style="font-weight:600;"),
            ui.tags.span(insight),
            class_="ai-insight",
        )

    @render.plot
    def gauge_icu_main():
        s = strain()
        if not s:
            return _gauge_fig(0, "ICU Occupancy", _CHART_MUTED)
        pct = (s.get("icu_rate") or 0) * 100
        occ, tot = s.get("icu_occupied", 0), s.get("icu_total", 50)
        color = "#dc2626" if pct >= 90 else "#ea580c" if pct >= 70 else "#16a34a"
        fig = _gauge_fig(pct, f"ICU Occupancy — {occ}/{tot} beds", color, 2)
        ax = fig.axes[0]
        ax.axvline(x=90, color="#dc2626", linestyle="--", alpha=0.5)
        ax.axvline(x=70, color="#ea580c", linestyle="--", alpha=0.5)
        return fig

    @render.ui
    def bed_grid_main():
        s = strain()
        occ, tot = (s.get("icu_occupied", 0), s.get("icu_total", 50)) if s else (0, 50)
        beds = "".join(
            f'<div class="bed-occ"></div>' if i < occ else '<div class="bed-free"></div>'
            for i in range(min(50, tot))
        )
        legend = '<div class="bed-legend"><span><span class="dot-occ"></span> Occupied</span><span><span class="dot-free"></span> Available</span></div>'
        return ui.HTML(f'<div class="card"><div class="card-title">BED STATUS</div><div class="bed-grid">{beds}</div>{legend}</div>')

    @render.plot
    def gauge_icu_small():
        s = strain()
        pct = (s.get("icu_rate") or 0) * 100 if s else 0
        color = "#dc2626" if pct >= 90 else "#ea580c" if pct >= 70 else "#16a34a"
        return _gauge_fig(pct, "ICU Capacity %", color)

    @render.plot
    def gauge_readmit_small():
        s = strain()
        if not s:
            return _gauge_fig(0, "Readmission Pressure %", "#3B82F6")
        total = s.get("total_patients", 1)
        high = s.get("high_readmission_count", 0)
        pct = min(100, (high / max(total, 1)) * 100)
        color = "#dc2626" if pct >= 15 else "#ea580c" if pct >= 5 else "#16a34a"
        return _gauge_fig(pct, "Readmission Pressure %", color)

    @render.plot
    def gauge_noshow_small():
        s = strain()
        if not s:
            return _gauge_fig(0, "Appointment Reliability %", _CHART_MUTED)
        total = s.get("total_patients", 1)
        noshow = s.get("likely_no_show_count", 0)
        pct = min(100, max(0, 100 - (noshow / max(total * 0.1, 1)) * 100))
        color = "#EF4444" if pct < 75 else "#F59E0B" if pct < 90 else "#10B981"
        return _gauge_fig(pct, "Appointment Reliability %", color)

    @render.ui
    def alerts_feed():
        s = strain()
        if not s:
            return ui.tags.div()
        pct = (s.get("icu_rate") or 0) * 100
        high = s.get("high_readmission_count", 0)
        alerts = []
        if pct >= 90:
            alerts.append(("🚨", "#ef4444", f"ICU CRITICAL: {pct:.0f}% occupancy"))
        elif pct >= 70:
            alerts.append(("⚠️", "#f59e0b", f"ICU ELEVATED: {pct:.0f}% occupancy"))
        if high > 100:
            alerts.append(("⚠️", "#f59e0b", f"{high} patients flagged for high readmission risk"))
        if not alerts:
            alerts.append(("✅", "#22c55e", "All systems operating within normal parameters"))
        return ui.TagList(
            ui.tags.div("ACTIVE ALERTS", class_="card-title"),
            *[
                ui.tags.div(
                    f"{icon} {msg}",
                    style=f"border-left:3px solid {color}; padding:10px 14px; margin:6px 0; background:var(--surface); border-radius:0 6px 6px 0;",
                )
                for icon, color, msg in alerts
            ],
        )

    # ─── Patients Tab (drill-down) ────────────────────────────────────────
    @reactive.calc
    def _patient_list_data():
        try:
            if input.main_nav() != "patients":
                return pd.DataFrame()
        except Exception:
            return pd.DataFrame()
        try:
            mode = input.patient_list_mode()
            search = (input.patient_search() or "").strip().lower()
            age_min = input.patient_age_min()
            age_max = input.patient_age_max()
            icu_only = input.patient_icu_only()
            high_risk_only = input.patient_high_risk_only()
        except Exception:
            mode, search, age_min, age_max = "all", "", 0, 100
            icu_only, high_risk_only = False, False
        if mode == "icu":
            df = safe(lambda: get_icu_patients(limit=500), pd.DataFrame())
        elif mode == "readmit":
            df = safe(lambda: get_high_readmission_patients(limit=500), pd.DataFrame())
        elif mode == "noshow":
            df = safe(lambda: get_likely_no_shows(days_ahead=7), pd.DataFrame())
        else:
            df = safe(lambda: get_patient_list_for_dashboard(limit=500), pd.DataFrame())
        if df.empty:
            return pd.DataFrame()
        df = df.copy()
        if search and "patient_id" in df.columns:
            df = df[df["patient_id"].astype(str).str.lower().str.contains(search, na=False)]
        if "age" in df.columns and age_min <= age_max:
            df = df[(pd.to_numeric(df["age"], errors="coerce").fillna(0) >= age_min) & (pd.to_numeric(df["age"], errors="coerce").fillna(999) <= age_max)]
        if icu_only and "icu_status" in df.columns:
            df = df[df["icu_status"].astype(str).str.lower().str.contains("yes", na=False)]
        if high_risk_only and "readmission_risk" in df.columns:
            df = df[pd.to_numeric(df["readmission_risk"], errors="coerce").fillna(0) >= 0.6]
        return df

    @render.ui
    def patient_list_header():
        try:
            if input.main_nav() != "patients":
                return ui.tags.div()
        except Exception:
            return ui.tags.div()
        df = _patient_list_data()
        try:
            mode = input.patient_list_mode()
        except Exception:
            mode = "all"
        labels = {"all": "All Patients", "icu": "ICU Patients", "readmit": "High Readmission Risk", "noshow": "Likely No-Shows"}
        label = labels.get(mode, "Patients")
        return ui.tags.h4(f"{label} ({len(df):,} rows)")

    @render.data_frame
    def patient_list_df():
        df = _patient_list_data()
        return render.DataGrid(df.head(200), height="400px")

    # ─── ICU Tab ───────────────────────────────────────────────────────────
    @render.plot
    def gauge_icu_tab():
        s = strain()
        pct = (s.get("icu_rate") or 0) * 100 if s else 0
        occ, tot = (s.get("icu_occupied", 0), s.get("icu_total", 50)) if s else (0, 50)
        color = "#dc2626" if pct >= 90 else "#ea580c" if pct >= 70 else "#16a34a"
        fig = _gauge_fig(pct, f"ICU Occupancy — {occ}/{tot} beds", color, 3)
        ax = fig.axes[0]
        ax.axvline(x=90, color="#dc2626", linestyle="--", alpha=0.5)
        ax.axvline(x=70, color="#ea580c", linestyle="--", alpha=0.5)
        return fig

    @render.ui
    def bed_grid_icu():
        s = strain()
        occ, tot = (s.get("icu_occupied", 0), s.get("icu_total", 50)) if s else (0, 50)
        beds = "".join(
            f'<div class="bed-occ"></div>' if i < occ else '<div class="bed-free"></div>'
            for i in range(min(50, tot))
        )
        legend = '<div class="bed-legend"><span><span class="dot-occ"></span> Occupied</span><span><span class="dot-free"></span> Available</span></div>'
        return ui.HTML(f'<div class="card"><div class="card-title">BED STATUS</div><div class="bed-grid">{beds}</div>{legend}</div>')

    @render.plot
    def icu_trend_plot():
        days = input.icu_days()
        df = safe(lambda: get_admissions_trend(days=days), pd.DataFrame())
        if df.empty or "date" not in df.columns:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            fig.patch.set_facecolor(_CHART_BG)
            ax.set_facecolor(_CHART_BG)
            return fig
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        fig, ax = plt.subplots(figsize=(10, 4))
        fig.patch.set_facecolor(_CHART_BG)
        ax.set_facecolor(_CHART_BG)
        ax.fill_between(df["date"], df["admissions"], alpha=0.25, color="#3B82F6")
        ax.plot(df["date"], df["admissions"], color="#3B82F6", marker="o", markersize=4)
        if "discharges" in df.columns:
            ax.plot(df["date"], df["discharges"], color="#16a34a", marker="s", markersize=3, label="Discharges")
        ax.set_xlabel("Date", color=_CHART_MUTED)
        ax.set_ylabel("Count", color=_CHART_MUTED)
        ax.grid(True, color=_CHART_GRID, linestyle="-", alpha=0.4, linewidth=0.5)
        ax.tick_params(colors=_CHART_MUTED)
        ax.legend()
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        fig.tight_layout()
        return fig

    # ─── Readmission Tab ───────────────────────────────────────────────────
    @render.ui
    def readmit_summary():
        s = strain()
        high = s.get("high_readmission_count", 0) if s else 0
        df = safe(lambda: get_high_readmission_patients(limit=100), pd.DataFrame())
        critical = len(df[df["readmission_risk"] >= 0.8]) if not df.empty and "readmission_risk" in df.columns else 0
        high_n = len(df[(df["readmission_risk"] >= 0.6) & (df["readmission_risk"] < 0.8)]) if not df.empty and "readmission_risk" in df.columns else 0
        return ui.layout_columns(
            ui.tags.p(f"**{high} patients** flagged for 30-day readmission risk ≥ 60%"),
            ui.tags.p(f"🔴 Critical (≥80%): {critical}"),
            ui.tags.p(f"🟡 High (60-80%): {high_n}"),
            col_widths=(4, 2, 2),
        )

    @render.ui
    def readmit_cards():
        df = safe(lambda: get_high_readmission_patients(limit=100), pd.DataFrame())
        sort_col = input.readmit_sort()
        filter_val = input.readmit_filter()
        if not df.empty and "readmission_risk" in df.columns:
            if filter_val == "critical":
                df = df[df["readmission_risk"] >= 0.8]
            elif filter_val == "high":
                df = df[(df["readmission_risk"] >= 0.6) & (df["readmission_risk"] < 0.8)]
            if sort_col == "risk":
                df = df.sort_values("readmission_risk", ascending=False)
            elif sort_col == "id" and "patient_id" in df.columns:
                df = df.sort_values("patient_id")
            elif sort_col == "admissions" and "admission_count" in df.columns:
                df = df.sort_values("admission_count", ascending=False)
        if df.empty:
            return ui.tags.p("No data available.", style="color:var(--muted);")
        cards = []
        for _, row in df.head(50).iterrows():
            risk = float(row.get("readmission_risk", 0))
            pct = risk * 100
            color = "#dc2626" if risk >= 0.8 else "#ea580c"
            badge = "CRITICAL" if risk >= 0.8 else "HIGH RISK"
            pid = row.get("patient_id", "—")
            cards.append(
                ui.tags.div(
                    ui.tags.div(
                        ui.tags.span(pid, style="font-family:var(--mono);"),
                        ui.tags.span(badge, style=f"background:{color}44; color:{color}; padding:3px 10px; border-radius:20px; font-size:0.75rem; margin-left:8px;"),
                        style="display:flex; justify-content:space-between; margin-bottom:8px;",
                    ),
                    ui.tags.div(
                        ui.tags.div(style=f"background:{color}; width:{min(100,pct):.0f}%; height:8px; border-radius:4px;"),
                        style="background:var(--bg); border-radius:4px; height:8px; margin-bottom:4px;",
                    ),
                    ui.tags.div(f"Risk: {pct:.1f}%", style="font-size:0.8rem; color:var(--muted);"),
                    style=f"background:var(--surface); border:1px solid var(--border); border-top:3px solid {color}; border-radius:10px; padding:16px;",
                )
            )
        return ui.tags.div(
            *cards,
            style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px;",
        )

    @render.plot
    def readmit_dist_plot():
        df = safe(lambda: get_high_readmission_patients(limit=100), pd.DataFrame())
        if df.empty or "readmission_risk" not in df.columns:
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            fig.patch.set_facecolor(_CHART_BG)
            return fig
        bins, ranges = ["0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"], [(0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
        counts = [len(df[(df["readmission_risk"] >= lo) & (df["readmission_risk"] < hi)]) for lo, hi in ranges]
        colors = ["#86efac", "#fdba74", "#ea580c", "#dc2626"]
        fig, ax = plt.subplots(figsize=(8, 3))
        fig.patch.set_facecolor(_CHART_BG)
        ax.set_facecolor(_CHART_BG)
        ax.bar(bins, counts, color=colors)
        ax.set_xlabel("Risk Range", color=_CHART_MUTED)
        ax.set_ylabel("Count", color=_CHART_MUTED)
        ax.grid(axis="y", color=_CHART_GRID, linestyle="-", alpha=0.4, linewidth=0.5)
        ax.tick_params(colors=_CHART_MUTED)
        fig.tight_layout()
        return fig

    # ─── No-Show Tab ───────────────────────────────────────────────────────
    @render.ui
    def noshow_summary():
        s = strain()
        n = s.get("likely_no_show_count", 0) if s else 0
        return ui.tags.p(f"**{n} appointments** at risk based on historical patterns")

    @render.plot
    def noshow_bar_plot():
        df = safe(get_department_no_show_rates, pd.DataFrame())
        if df.empty or "no_show_rate" not in df.columns:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            fig.patch.set_facecolor(_CHART_BG)
            return fig
        dept_col = "department" if "department" in df.columns else df.columns[0]
        df = df.sort_values("no_show_rate", ascending=False)
        colors = ["#dc2626" if r > 0.20 else "#ea580c" if r > 0.10 else "#16a34a" for r in df["no_show_rate"]]
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor(_CHART_BG)
        ax.set_facecolor(_CHART_BG)
        ax.barh(df[dept_col].astype(str).str.capitalize(), df["no_show_rate"] * 100, color=colors)
        ax.set_xlabel("No-Show Rate (%)", color=_CHART_MUTED)
        ax.grid(axis="x", color=_CHART_GRID, linestyle="-", alpha=0.4, linewidth=0.5)
        ax.tick_params(colors=_CHART_MUTED)
        fig.tight_layout()
        return fig

    @render.ui
    def noshow_stats():
        df = safe(get_department_no_show_rates, pd.DataFrame())
        s = strain()
        n = s.get("likely_no_show_count", 0) if s else 0
        if df.empty or "no_show_rate" not in df.columns:
            return ui.TagList(
                ui.tags.div("Highest Risk Dept: N/A", class_="card"),
                ui.tags.div("Lowest Risk Dept: N/A", class_="card"),
                ui.tags.div(f"Patients at Risk: {n}", class_="card"),
            )
        dept_col = "department" if "department" in df.columns else df.columns[0]
        high, low = df.iloc[0], df.iloc[-1]
        overall = df["no_show_rate"].mean() * 100
        return ui.TagList(
            ui.tags.div(f"Highest: {str(high.get(dept_col,'N/A')).capitalize()} ({high['no_show_rate']*100:.1f}%)", class_="card"),
            ui.tags.div(f"Lowest: {str(low.get(dept_col,'N/A')).capitalize()} ({low['no_show_rate']*100:.1f}%)", class_="card"),
            ui.tags.div(f"Overall No-Show Rate: {overall:.1f}%", class_="card"),
            ui.tags.div(f"Patients at Risk: {n}", class_="card"),
        )

    @render.data_frame
    def noshow_df():
        df = safe(get_likely_no_shows, pd.DataFrame())
        return render.DataGrid(df.head(50), height="300px")

    # ─── Patient Twin Tab ──────────────────────────────────────────────────
    @render.ui
    def twin_content():
        pid = loaded_pid()
        if not pid:
            return ui.tags.div("Select a patient and click Load Patient Twin.", class_="card")
        hist = safe(lambda: get_patient_history(pid), {})
        dem = hist.get("demographics", {})
        risk_df = hist.get("risk_scores", pd.DataFrame())
        admissions = hist.get("admissions", pd.DataFrame())

        parts = []
        if dem:
            parts.append(ui.tags.h4("Demographics"))
            for k, v in list(dem.items())[:9]:
                parts.append(ui.tags.p(ui.tags.strong(k.replace("_", " ").title() + ": "), str(v)))

        if risk_df is not None and isinstance(risk_df, pd.DataFrame) and not risk_df.empty:
            parts.append(ui.tags.h4("Risk Profile"))
            chips = []
            for col in ["readmission_risk", "icu_risk", "no_show_risk"]:
                if col in risk_df.columns:
                    val = risk_df[col].iloc[0]
                    color = "#dc2626" if val >= 0.8 else "#ea580c" if val >= 0.5 else "#16a34a"
                    label = col.replace("_risk", "").replace("_", " ").title()
                    chips.append(ui.tags.span(f"{label}: {val:.2f}", style=f"background:{color}22; border:1px solid {color}; padding:6px 14px; border-radius:20px; margin-right:8px;"))
            parts.append(ui.tags.div(*chips, style="margin:8px 0;"))

        parts.append(ui.tags.h4("AI Risk Explanation"))
        parts.append(ui.output_ui("twin_ai_explanation"))

        parts.append(ui.output_plot("twin_vitals_plot"))
        parts.append(ui.output_data_frame("twin_admissions_df"))
        return ui.TagList(*parts)

    @render.ui
    def twin_ai_explanation():
        pid = loaded_pid()
        if not pid:
            return ui.tags.p("Select a patient to see AI risk explanation.", style="color:var(--muted);")
        hist = safe(lambda: get_patient_history(pid), {})
        try:
            explanation = explain_patient_risk(pid, hist)
        except Exception as e:
            explanation = f"AI explanation temporarily unavailable: {e}"
        return ui.tags.div(
            ui.tags.p(explanation, style="white-space:pre-wrap; font-size:14px; line-height:1.6;"),
            class_="ai-insight",
        )

    @render.plot
    def twin_vitals_plot():
        pid = loaded_pid()
        if not pid:
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.text(0.5, 0.5, "Select a patient", ha="center", va="center")
            fig.patch.set_facecolor(_CHART_BG)
            return fig
        hist = safe(lambda: get_patient_history(pid), {})
        vitals = hist.get("vitals", pd.DataFrame())
        if vitals is None or not isinstance(vitals, pd.DataFrame) or vitals.empty:
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.text(0.5, 0.5, "No vitals data", ha="center", va="center")
            fig.patch.set_facecolor(_CHART_BG)
            return fig
        v = vitals.tail(20)
        fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
        fig.patch.set_facecolor(_CHART_BG)
        for ax in axes:
            ax.set_facecolor(_CHART_BG)
            ax.grid(True, color=_CHART_GRID, linestyle="-", alpha=0.4, linewidth=0.5)
            ax.tick_params(colors=_CHART_MUTED)
        if "heart_rate" in v.columns:
            axes[0].plot(v["heart_rate"], color="#ea580c", marker="o", markersize=4)
            axes[0].axhline(100, color="#dc2626", linestyle="--", alpha=0.5)
            axes[0].axhline(60, color="#dc2626", linestyle="--", alpha=0.5)
            axes[0].set_ylabel("Heart Rate (bpm)", color=_CHART_MUTED)
        if "oxygen_saturation" in v.columns:
            axes[1].plot(v["oxygen_saturation"], color="#3B82F6", marker="o", markersize=4)
            axes[1].axhline(95, color="#dc2626", linestyle="--", alpha=0.5)
            axes[1].set_ylabel("SpO2 (%)", color=_CHART_MUTED)
        fig.tight_layout()
        return fig

    @render.data_frame
    def twin_admissions_df():
        pid = loaded_pid()
        if not pid:
            return render.DataGrid(pd.DataFrame(), height="200px")
        hist = safe(lambda: get_patient_history(pid), {})
        adm = hist.get("admissions", pd.DataFrame())
        if adm is None or not isinstance(adm, pd.DataFrame) or adm.empty:
            return render.DataGrid(pd.DataFrame(), height="200px")
        return render.DataGrid(adm, height="200px")

    # ─── Trends Tab ────────────────────────────────────────────────────────
    @render.plot
    def trend_main_plot():
        days = input.trend_days()
        metric = input.trend_metric()
        show_ma = input.trend_ma()
        df = safe(lambda: get_admissions_trend(days=days), pd.DataFrame())
        if df.empty or "date" not in df.columns:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            fig.patch.set_facecolor(_CHART_BG)
            return fig
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        fig, ax = plt.subplots(figsize=(10, 4))
        fig.patch.set_facecolor(_CHART_BG)
        ax.set_facecolor(_CHART_BG)
        if metric in ("both", "admissions") and "admissions" in df.columns:
            ax.fill_between(df["date"], df["admissions"], alpha=0.25, color="#3B82F6")
            ax.plot(df["date"], df["admissions"], color="#3B82F6", marker="o", markersize=4, label="Admissions")
        if metric in ("both", "discharges") and "discharges" in df.columns:
            ax.plot(df["date"], df["discharges"], color="#16a34a", marker="s", markersize=3, label="Discharges")
        if show_ma and "admissions" in df.columns and len(df) >= 7:
            ma = df["admissions"].rolling(7, min_periods=1).mean()
            ax.plot(df["date"], ma, color="#ea580c", linestyle="--", linewidth=1.5, label="7-day avg")
        ax.set_xlabel("Date", color=_CHART_MUTED)
        ax.set_ylabel("Count", color=_CHART_MUTED)
        ax.grid(True, color=_CHART_GRID, linestyle="-", alpha=0.4, linewidth=0.5)
        ax.legend()
        ax.tick_params(colors=_CHART_MUTED)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        fig.tight_layout()
        return fig

    @render.plot
    def trend_net_plot():
        days = input.trend_days()
        df = safe(lambda: get_admissions_trend(days=days), pd.DataFrame())
        if df.empty or "date" not in df.columns:
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            fig.patch.set_facecolor(_CHART_BG)
            return fig
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        discharges = df["discharges"] if "discharges" in df.columns else pd.Series(0, index=df.index)
        net = df["admissions"] - discharges
        colors = ["#16a34a" if n <= 0 else "#dc2626" for n in net]
        fig, ax = plt.subplots(figsize=(10, 3))
        fig.patch.set_facecolor(_CHART_BG)
        ax.set_facecolor(_CHART_BG)
        ax.bar(df["date"], net, color=colors)
        ax.axhline(0, color=_CHART_MUTED, linewidth=1)
        ax.grid(axis="y", color=_CHART_GRID, linestyle="-", alpha=0.4, linewidth=0.5)
        ax.set_xlabel("Date", color=_CHART_MUTED)
        ax.set_ylabel("Net Flow", color=_CHART_MUTED)
        ax.tick_params(colors=_CHART_MUTED)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        fig.tight_layout()
        return fig

    @render.ui
    def trend_stats():
        days = input.trend_days()
        df = safe(lambda: get_admissions_trend(days=days), pd.DataFrame())
        if df.empty or "admissions" not in df.columns:
            return ui.tags.div()
        avg = df["admissions"].mean()
        total = df["admissions"].sum()
        peak_idx = df["admissions"].idxmax()
        peak_day = str(df.loc[peak_idx, "date"])[:10] if len(df) else "N/A"
        direction = "↑ Increasing" if df["admissions"].iloc[-1] > df["admissions"].iloc[0] else "↓ Decreasing"
        return ui.layout_columns(
            ui.tags.div(ui.tags.div("Avg Daily", class_="kpi-label"), ui.tags.div(f"{avg:.1f}", class_="kpi-value"), class_="kpi-card"),
            ui.tags.div(ui.tags.div("Total", class_="kpi-label"), ui.tags.div(f"{int(total):,}", class_="kpi-value"), class_="kpi-card"),
            ui.tags.div(ui.tags.div("Peak Day", class_="kpi-label"), ui.tags.div(peak_day, class_="kpi-value"), class_="kpi-card"),
            ui.tags.div(ui.tags.div("Trend", class_="kpi-label"), ui.tags.div(direction, class_="kpi-value"), class_="kpi-card"),
            col_widths=(3, 3, 3, 3),
            gap="20px",
        )

    # ─── AI Assistant Tab ──────────────────────────────────────────────────
    @reactive.effect
    @reactive.event(input.ai_ask)
    def _on_ai_ask():
        q = input.ai_question()
        if not q or not str(q).strip():
            return
        s = strain()
        try:
            ans = answer_user_question(str(q).strip(), s or {})
        except Exception as e:
            ans = f"AI unavailable: {e}"
        hist = ai_history()
        new_hist = hist + [(q, str(ans))]
        ai_history.set(new_hist[-5:] if len(new_hist) > 5 else new_hist)

    @render.ui
    def ai_answer():
        hist = ai_history()
        if not hist:
            return ui.tags.div("Ask a question above and click Ask AI.", style="color:var(--muted);")
        from html import escape
        return ui.TagList(
            *[
                ui.tags.div(
                    ui.tags.div(ui.tags.strong("Q: "), escape(str(q)), style="margin-bottom:4px;"),
                    ui.tags.div(ui.tags.strong("A: "), escape(str(a)), style="background:var(--surface2); padding:12px; border-radius:8px; border:1px solid var(--border); margin-bottom:16px;"),
                    style="margin-bottom:16px;",
                )
                for q, a in reversed(hist)
            ],
        )


app = App(app_ui, server)

if __name__ == "__main__":
    from shiny import run_app
    run_app(app, port=8000, launch_browser=True)