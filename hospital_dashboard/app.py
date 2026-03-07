"""
Patient Digital Twin — Stakeholder Decision Dashboard

Action-oriented for clinical and operational leaders:
- Readmission Risk: Who to prioritize + Patient Comparison
- ICU Capacity: When to act
- Post-Discharge Vitals: Monitor & intervene early

Each section includes descriptive statistics, visuals, and AI recommendations.
"""

import pandas as pd
from shiny import App, reactive, render, ui

from database_connection import get_patients
from hospital_analytics import (
    get_icu_occupancy,
    get_high_readmission_patients,
    get_admissions_trend,
    get_patient_history,
    predict_icu_capacity_reach_90,
    get_similar_patients,
    get_descriptive_stats,
    get_vitals_summary,
)
from hospital_ai_agent import (
    _html_report_readmission,
    _html_report_icu,
    _html_report_comparison,
    summarize_readmission_page,
    summarize_icu_page,
    summarize_comparison_page,
    summarize_vitals_page,
)


def safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _stats_table_html(stats: dict, title: str = "Descriptive Statistics") -> str:
    """Render descriptive stats as HTML table."""
    if not stats:
        return ""
    from html import escape
    parts = [f'<h5>{escape(title)}</h5><table class="table table-sm table-bordered"><thead><tr><th>Variable</th><th>Count</th><th>Mean</th><th>SD</th><th>Min</th><th>Max</th></tr></thead><tbody>']
    for var, v in stats.items():
        parts.append(f"<tr><td>{escape(str(var))}</td><td>{v.get('count','')}</td><td>{v.get('mean','')}</td><td>{v.get('sd','')}</td><td>{v.get('min','')}</td><td>{v.get('max','')}</td></tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


CUSTOM_CSS = """
:root { --primary: #0d9488; --primary-dark: #0f766e; --accent: #06b6d4; --bg: #f8fafc; --text: #1e293b; --muted: #64748b; }
body { background: var(--bg); font-family: 'Segoe UI', system-ui, sans-serif; color: var(--text); }
.navbar { background: linear-gradient(90deg, #0d9488, #0891b2) !important; box-shadow: 0 2px 12px rgba(13,148,136,0.25); }
.navbar .nav-link { color: rgba(255,255,255,0.95) !important; font-weight: 500; }
.navbar .nav-link:hover { color: #fff !important; background: rgba(255,255,255,0.2); border-radius: 6px; }
.navbar .nav-link.active { background: rgba(255,255,255,0.3); border-radius: 6px; color: #fff !important; }
.bslib-nav-content { padding: 1.5rem; }
.card { border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }
.card-header { background: linear-gradient(135deg, rgba(13,148,136,0.08), rgba(6,182,212,0.05)); font-weight: 600; color: var(--primary-dark); border-radius: 12px 12px 0 0; }
.report-section { padding: 0.5rem 0; }
.report-section h4 { color: var(--primary-dark); margin-bottom: 0.5rem; }
.report-section h5 { color: var(--accent); font-size: 1rem; margin-top: 1rem; }
.ai-summary-box { background: linear-gradient(135deg, rgba(13,148,136,0.06), rgba(6,182,212,0.04)); border-left: 4px solid var(--primary); padding: 1rem; border-radius: 0 8px 8px 0; margin-top: 1rem; }
.ai-summary-box h5 { color: var(--primary); margin-bottom: 0.5rem; }
.action-banner { background: linear-gradient(135deg, #fef3c7, #fde68a); border-left: 4px solid #f59e0b; padding: 1rem; border-radius: 0 8px 8px 0; margin-bottom: 1rem; }
.action-banner h5 { color: #92400e; margin-bottom: 0.5rem; }
"""


def make_card(title, content):
    return ui.card(ui.card_header(title), content, full_screen=True)


app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.title("Patient Digital Twin — Decision Dashboard"),
        ui.tags.style(CUSTOM_CSS),
        ui.tags.link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css"),
    ),
    ui.page_navbar(
        # ---- Page 1: Readmission Risk (includes Patient Comparison) ----
        ui.nav_panel(
            "Readmission Risk",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.tags.h5("Filters"),
                    ui.input_slider("q1_limit", "Patients to show", min=5, max=50, value=15, step=5),
                    ui.input_select("q1_sort", "Sort by", choices={"readmission_risk": "Readmission Risk", "icu_risk": "ICU Risk", "no_show_risk": "No-Show Risk"}, selected="readmission_risk"),
                    ui.hr(),
                    ui.tags.h5("Compare Patient"),
                    ui.input_select("q3_patient", "Patient ID", choices={"": "Select..."}, selected=""),
                    ui.input_action_button("q3_load", "Compare to Similar Cases", class_="btn-primary"),
                    title="Options",
                    open="always",
                ),
                ui.layout_columns(
                    ui.value_box("High-Risk Count", ui.output_text("q1_count"), theme="danger", height="100px"),
                    ui.value_box("Action Threshold", "≥ 0.6", theme="warning", height="100px"),
                    col_widths=(6, 6),
                ),
                ui.output_ui("q1_action_banner"),
                make_card(
                    "Descriptive Statistics — High-Risk Cohort",
                    ui.output_ui("q1_stats"),
                ),
                make_card(
                    "Patients to Prioritize — Highest 30-Day Readmission Risk",
                    ui.output_ui("q1_report"),
                ),
                make_card(
                    "Compare Patient to Similar Historical Cases",
                    ui.output_ui("q3_report"),
                ),
                make_card(
                    "Admission Trend (Last 14 Days)",
                    ui.output_plot("q1_trend"),
                ),
                make_card(
                    "AI Summary — What to Do",
                    ui.output_ui("q1_ai_summary"),
                ),
            ),
        ),
        # ---- Page 2: ICU Capacity ----
        ui.nav_panel(
            "ICU Capacity",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.tags.h5("Options"),
                    ui.input_slider("q2_days", "Trend window (days)", min=7, max=30, value=14, step=1),
                    title="Settings",
                    open="always",
                ),
                ui.layout_columns(
                    ui.value_box("ICU Occupancy", ui.output_text("q2_icu"), theme="primary", height="100px"),
                    ui.value_box("Days to 90%", ui.output_text("q2_days_to_90"), theme="warning", height="100px"),
                    col_widths=(6, 6),
                ),
                ui.output_ui("q2_action_banner"),
                make_card(
                    "Descriptive Statistics — Admissions Trend",
                    ui.output_ui("q2_stats"),
                ),
                make_card(
                    "ICU Capacity Forecast",
                    ui.output_ui("q2_report"),
                ),
                make_card(
                    "Admissions Trend",
                    ui.output_plot("q2_trend"),
                ),
                make_card(
                    "AI Summary — What to Do",
                    ui.output_ui("q2_ai_summary"),
                ),
            ),
        ),
        # ---- Page 3: Post-Discharge Vitals ----
        ui.nav_panel(
            "Post-Discharge Vitals",
            ui.layout_columns(
                ui.value_box("Vital Records", ui.output_text("vitals_n"), theme="info", height="100px"),
                ui.value_box("Patients Monitored", ui.output_text("vitals_patients"), theme="primary", height="100px"),
                col_widths=(6, 6),
            ),
            make_card(
                "Descriptive Statistics — Vitals (from monitors/sensors)",
                ui.output_ui("vitals_stats"),
            ),
            make_card(
                "Vitals Distribution",
                ui.output_plot("vitals_plot"),
            ),
            make_card(
                "AI Summary — What to Do",
                ui.output_ui("vitals_ai_summary"),
            ),
        ),
        title=ui.tags.div(ui.tags.i(class_="bi bi-heart-pulse-fill"), " Patient Digital Twin", class_="logo-header"),
        id="main_nav",
        selected="Readmission Risk",
    ),
)


def server(input, output, session):
    @reactive.effect
    def _():
        ids = safe(lambda: sorted(get_patients()["patient_id"].astype(str).unique().tolist())[:500], [])
        choices = {"": "Select patient..."}
        if ids:
            choices.update({i: i for i in ids})
            ui.update_select("q3_patient", choices=choices, selected=ids[0], session=session)
        else:
            ui.update_select("q3_patient", choices=choices, session=session)

    # ---- Q1: Readmission ----
    @render.text
    def q1_count():
        limit = input.q1_limit()
        df = safe(lambda: get_high_readmission_patients(limit=limit), pd.DataFrame())
        return str(len(df))

    @render.ui
    def q1_action_banner():
        df = safe(lambda: get_high_readmission_patients(limit=20), pd.DataFrame())
        n = len(df)
        if n == 0:
            return ui.tags.div()
        return ui.tags.div(
            ui.tags.h5("What to do now"),
            ui.tags.p(f"Prioritize {n} high-risk patients for discharge planning, care coordination, and follow-up calls. Use the Patient Comparison below to learn from similar cases."),
            class_="action-banner",
        )

    @render.ui
    def q1_stats():
        df = safe(lambda: get_high_readmission_patients(limit=100), pd.DataFrame())
        cols = [c for c in ["readmission_risk", "icu_risk", "no_show_risk", "age", "bmi"] if c in df.columns]
        stats = get_descriptive_stats(df, cols)
        return ui.HTML(_stats_table_html(stats, "High-Risk Cohort"))

    @render.ui
    def q1_report():
        limit = input.q1_limit()
        df = safe(lambda: get_high_readmission_patients(limit=limit), pd.DataFrame())
        sort_col = input.q1_sort()
        if not df.empty and sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=False).head(limit)
        html = _html_report_readmission(df, limit)
        return ui.HTML(html)

    @render.plot
    def q1_trend():
        trend = safe(lambda: get_admissions_trend(days=14), pd.DataFrame())
        if trend.empty:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            return fig
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.fill_between(trend["date"], trend["admissions"], alpha=0.3, color="#0d9488")
        ax.plot(trend["date"], trend["admissions"], color="#0891b2", marker="o", markersize=4)
        if "discharges" in trend.columns:
            ax.plot(trend["date"], trend["discharges"], color="#f59e0b", marker="s", markersize=3, label="Discharges")
        ax.set_xlabel("Date")
        ax.set_ylabel("Count")
        ax.legend()
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        return fig

    @render.ui
    def q1_ai_summary():
        limit = input.q1_limit()
        df = safe(lambda: get_high_readmission_patients(limit=limit), pd.DataFrame())
        try:
            text = summarize_readmission_page(df, limit)
            return ui.tags.div(ui.tags.h5("AI Summary — What to Do"), ui.tags.p(text), class_="ai-summary-box")
        except Exception as e:
            return ui.tags.div(ui.tags.p(f"AI unavailable: {e}"), class_="ai-summary-box")

    # ---- Patient Comparison (in Readmission section) ----
    @render.ui
    @reactive.event(input.q3_load)
    def q3_report():
        pid = input.q3_patient()
        if not pid or pid == "":
            return ui.tags.p("Select a patient and click Compare to Similar Cases.")
        sim = safe(lambda: get_similar_patients(pid, n=5), {"similar": [], "patient_profile": {}, "note": "Error"})
        html = _html_report_comparison(sim)
        try:
            from html import escape
            ai_text = summarize_comparison_page(sim)
            html += f'<div class="ai-summary-box mt-3"><h5>AI Summary — What to Consider</h5><p>{escape(str(ai_text))}</p></div>'
        except Exception:
            pass
        return ui.HTML(html)

    # ---- Q2: ICU Capacity ----
    @render.text
    def q2_icu():
        o = safe(get_icu_occupancy, {"total": 0, "occupied": 0, "rate": 0})
        return f"{o['occupied']} / {o['total']} ({o['rate']*100:.1f}%)"

    @render.text
    def q2_days_to_90():
        pred = safe(predict_icu_capacity_reach_90, {})
        if pred.get("already_at_risk"):
            return "At risk now"
        d = pred.get("estimated_days")
        return f"~{d:.0f} days" if d else "—"

    @render.ui
    def q2_action_banner():
        pred = safe(predict_icu_capacity_reach_90, {})
        if pred.get("already_at_risk"):
            return ui.tags.div(
                ui.tags.h5("What to do now"),
                ui.tags.p("ICU is at or above 90% capacity. Escalate: consider transfer protocols, elective deferral, or staffing adjustments."),
                class_="action-banner",
            )
        d = pred.get("estimated_days")
        if d is not None and d < 3:
            return ui.tags.div(
                ui.tags.h5("What to do now"),
                ui.tags.p(f"ICU may reach 90% in ~{d:.0f} days. Prepare transfer protocols and monitor admissions closely."),
                class_="action-banner",
            )
        return ui.tags.div()

    @render.ui
    def q2_stats():
        days = input.q2_days()
        trend = safe(lambda: get_admissions_trend(days=days), pd.DataFrame())
        if trend.empty:
            return ui.tags.p("No trend data.")
        stats = get_descriptive_stats(trend, ["admissions", "discharges"] if "discharges" in trend.columns else ["admissions"])
        return ui.HTML(_stats_table_html(stats, "Admissions Trend"))

    @render.ui
    def q2_report():
        pred = safe(predict_icu_capacity_reach_90, {"forecast_note": "N/A", "current_occupied": 0, "total_beds": 50})
        icu = safe(get_icu_occupancy, {"total": 50, "occupied": 0})
        return ui.HTML(_html_report_icu(pred, icu))

    @render.plot
    def q2_trend():
        days = input.q2_days()
        trend = safe(lambda: get_admissions_trend(days=days), pd.DataFrame())
        if trend.empty:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            return fig
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(trend["date"], trend["admissions"], color="#0d9488", marker="o", markersize=4, label="Admissions")
        if "discharges" in trend.columns:
            ax.plot(trend["date"], trend["discharges"], color="#f59e0b", marker="s", markersize=3, label="Discharges")
        ax.set_xlabel("Date")
        ax.set_ylabel("Count")
        ax.legend()
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        return fig

    @render.ui
    def q2_ai_summary():
        pred = safe(predict_icu_capacity_reach_90, {})
        icu = safe(get_icu_occupancy, {})
        trend = safe(lambda: get_admissions_trend(days=14), pd.DataFrame())
        trend_data = trend.to_dict(orient="records") if not trend.empty else []
        try:
            text = summarize_icu_page(pred, icu, trend_data)
            return ui.tags.div(ui.tags.h5("AI Summary — What to Do"), ui.tags.p(text), class_="ai-summary-box")
        except Exception as e:
            return ui.tags.div(ui.tags.p(f"AI unavailable: {e}"), class_="ai-summary-box")

    # ---- Vitals ----
    @render.text
    def vitals_n():
        s = safe(lambda: get_vitals_summary(3000), {"n_records": 0})
        return str(s.get("n_records", 0))

    @render.text
    def vitals_patients():
        s = safe(lambda: get_vitals_summary(3000), {"n_patients": 0})
        return str(s.get("n_patients", 0))

    @render.ui
    def vitals_stats():
        s = safe(lambda: get_vitals_summary(3000), {"stats": {}})
        stats = s.get("stats", {})
        return ui.HTML(_stats_table_html(stats, "Post-Discharge Vitals (monitors/sensors)"))

    @render.plot
    def vitals_plot():
        s = safe(lambda: get_vitals_summary(3000), {"stats": {}, "sample": pd.DataFrame()})
        vitals = s.get("sample", pd.DataFrame())
        if vitals.empty:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.text(0.5, 0.5, "No vitals data", ha="center", va="center")
            return fig
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 2, figsize=(10, 8))
        axes = axes.flatten()
        cols = [c for c in ["heart_rate", "oxygen_saturation", "systolic_bp", "temperature"] if c in vitals.columns][:4]
        for i, col in enumerate(cols):
            ax = axes[i]
            ax.hist(vitals[col].dropna(), bins=30, color="#0d9488", alpha=0.7, edgecolor="white")
            ax.set_title(col.replace("_", " ").title())
            ax.set_xlabel(col)
        for j in range(len(cols), 4):
            axes[j].axis("off")
        fig.tight_layout()
        return fig

    @render.ui
    def vitals_ai_summary():
        s = safe(lambda: get_vitals_summary(3000), {})
        try:
            text = summarize_vitals_page(s)
            return ui.tags.div(ui.tags.h5("AI Summary — What to Do"), ui.tags.p(text), class_="ai-summary-box")
        except Exception as e:
            return ui.tags.div(ui.tags.p(f"AI unavailable: {e}"), class_="ai-summary-box")


app = App(app_ui, server)

if __name__ == "__main__":
    from shiny import run_app
    run_app(app, launch_browser=True)
