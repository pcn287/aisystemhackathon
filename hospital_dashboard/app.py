"""
Layer 5 — Shiny Dashboard Application

PATIENT DIGITAL TWIN HOSPITAL OPERATIONS DASHBOARD

Sections: Hospital Status Summary, ICU Capacity, High Readmission Risk,
Appointment No-Show Risk, Patient Digital Twin Viewer, Operational Trends,
AI Hospital Assistant (chat).
"""

import pandas as pd
from shiny import App, reactive, render, ui

# Local modules (run from hospital_dashboard directory)
from database_connection import (
    get_patients,
    get_admissions,
    get_icu_beds,
)
from hospital_analytics import (
    get_total_patients,
    get_icu_occupancy,
    get_high_readmission_patients,
    get_likely_no_shows,
    get_admissions_trend,
    get_department_no_show_rates,
    get_patient_history,
)
from hospital_ai_agent import (
    generate_operational_summary,
    explain_patient_risk,
    predict_capacity_alerts,
    answer_user_question,
)


def safe_total_patients():
    try:
        return get_total_patients()
    except Exception:
        return 0


def safe_icu_occupancy():
    try:
        return get_icu_occupancy()
    except Exception:
        return {"total": 0, "occupied": 0, "rate": 0.0}


def safe_high_readmission(limit=20):
    try:
        return get_high_readmission_patients(limit=limit)
    except Exception:
        return pd.DataFrame()


def safe_likely_no_shows():
    try:
        return get_likely_no_shows(days_ahead=1)
    except Exception:
        return pd.DataFrame()


def safe_admissions_trend(days=30):
    try:
        return get_admissions_trend(days=days)
    except Exception:
        return pd.DataFrame()


def safe_department_no_show():
    try:
        return get_department_no_show_rates()
    except Exception:
        return pd.DataFrame()


def safe_patient_history(patient_id):
    try:
        return get_patient_history(patient_id)
    except Exception:
        return {"demographics": {}, "vitals": pd.DataFrame(), "admissions": pd.DataFrame(), "risk_scores": pd.DataFrame()}


def safe_patient_ids():
    try:
        df = get_patients()
        if df.empty or "patient_id" not in df.columns:
            return []
        ids = df["patient_id"].astype(str).unique().tolist()
        return sorted(ids)[:500]
    except Exception:
        return []


# ---- UI ----
app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.title("Patient Digital Twin Hospital Operations Dashboard"),
        ui.tags.style(
            """
            .navbar { background: linear-gradient(135deg, #1a365d 0%, #2c5282 100%); }
            .bslib-value-box { border-radius: 8px; }
            """
        ),
    ),
    ui.page_navbar(
        # --- Panel: Hospital Status Summary ---
        ui.nav_panel(
            "Summary",
            ui.layout_columns(
                ui.value_box(
                    "Total Patients",
                    ui.output_text("kpi_total"),
                    theme="primary",
                    height="120px",
                ),
                ui.value_box(
                    "ICU Occupancy",
                    ui.output_text("kpi_icu"),
                    theme="info",
                    height="120px",
                ),
                ui.value_box(
                    "High Readmission Risk Patients",
                    ui.output_text("kpi_readmission"),
                    theme="warning",
                    height="120px",
                ),
                ui.value_box(
                    "Likely No-Shows Tomorrow",
                    ui.output_text("kpi_noshow"),
                    theme="danger",
                    height="120px",
                ),
                col_widths=(3, 3, 3, 3),
                row_heights="auto",
            ),
            ui.hr(),
            ui.h5("Operational Summary"),
            ui.output_ui("operational_summary"),
        ),
        # --- Panel: ICU Capacity ---
        ui.nav_panel(
            "ICU Capacity",
            ui.output_ui("icu_alert_banner"),
            ui.layout_columns(
                ui.card(
                    ui.card_header("ICU Bed Occupancy (50 beds; ≥90% = high operational risk)"),
                    ui.output_ui("icu_gauge"),
                    full_screen=True,
                ),
                col_widths=6,
            ),
            ui.card(
                ui.card_header("ICU Occupancy Trend (Daily)"),
                ui.output_plot("icu_trend_plot"),
                full_screen=True,
            ),
        ),
        # --- Panel: High Readmission Risk ---
        ui.nav_panel(
            "High Readmission Risk",
            ui.card(
                ui.card_header("Patients Flagged with 30-Day Readmission Risk ≥ 0.6 (Top 20)"),
                ui.output_data_frame("readmission_table"),
                full_screen=True,
            ),
        ),
        # --- Panel: No-Show Risk ---
        ui.nav_panel(
            "No-Show Risk",
            ui.card(
                ui.card_header("Departments by No-Show Rate"),
                ui.output_data_frame("noshow_table"),
                full_screen=True,
            ),
        ),
        # --- Panel: Patient Digital Twin Viewer ---
        ui.nav_panel(
            "Patient Twin",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.input_select(
                        "patient_id",
                        "Select Patient ID",
                        choices={"": "Select patient..."},
                        selected="",
                    ),
                    ui.input_action_button("load_twin", "Load Patient Twin", class_="btn-primary"),
                    title="Patient",
                    open="always",
                ),
                ui.output_ui("twin_demographics"),
                ui.output_data_frame("twin_vitals"),
                ui.output_data_frame("twin_admissions"),
                ui.output_data_frame("twin_risk_scores"),
                ui.output_ui("twin_ai_explanation"),
            ),
        ),
        # --- Panel: Operational Trends ---
        ui.nav_panel(
            "Trends",
            ui.card(
                ui.card_header("Daily Admissions & Discharges"),
                ui.output_plot("trend_plot"),
                full_screen=True,
            ),
            ui.card(
                ui.card_header("ICU Utilization (from admissions trend)"),
                ui.output_plot("icu_util_plot"),
                full_screen=True,
            ),
        ),
        # --- Panel: AI Assistant ---
        ui.nav_panel(
            "AI Assistant",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.tags.p("Ask questions about patients, ICU capacity, no-shows, or operations."),
                    ui.input_text_area(
                        "user_question",
                        "Your question",
                        placeholder="e.g. Which patients are most likely to be readmitted this week?",
                        rows=4,
                    ),
                    ui.input_action_button("ask_ai", "Ask AI", class_="btn-primary"),
                    title="Chat",
                    open="always",
                ),
                ui.output_ui("ai_answer"),
            ),
        ),
        title=ui.tags.span("PATIENT DIGITAL TWIN HOSPITAL OPERATIONS DASHBOARD", style="font-weight: 700;"),
        id="main_nav",
        selected="Summary",
        position="static-top",
    ),
)


def server(input, output, session):
    # Populate patient ID choices when session starts
    @reactive.effect
    def _():
        ids = safe_patient_ids()
        choices = {"": "Select patient..."}
        if ids:
            choices.update({i: i for i in ids})
            ui.update_select("patient_id", choices=choices, selected=ids[0], session=session)
        else:
            ui.update_select("patient_id", choices=choices, session=session)

    # ---- Summary KPIs ----
    @render.text
    def kpi_total():
        return str(safe_total_patients())

    @render.text
    def kpi_icu():
        o = safe_icu_occupancy()
        return f"{o['occupied']} / {o['total']} ({o['rate']*100:.1f}%)"

    @render.text
    def kpi_readmission():
        return str(len(safe_high_readmission(limit=100)))

    @render.text
    def kpi_noshow():
        return str(len(safe_likely_no_shows()))

    @render.ui
    def operational_summary():
        try:
            text = generate_operational_summary()
            return ui.tags.p(text)
        except Exception as e:
            return ui.tags.p(f"Summary unavailable: {e}", style="color: #888;")

    # ---- ICU ----
    @render.ui
    def icu_alert_banner():
        o = safe_icu_occupancy()
        if o.get("high_operational_risk"):
            return ui.tags.div(
                ui.tags.div(
                    "High operational risk: ICU occupancy ≥ 90%. Consider capacity escalation or transfer options.",
                    class_="alert alert-danger",
                    role="alert",
                ),
                style="margin-bottom: 1rem;",
            )
        return ui.tags.div()

    @render.ui
    def icu_gauge():
        o = safe_icu_occupancy()
        pct = o["rate"] * 100
        color = "danger" if pct >= 90 else "warning" if pct >= 70 else "success"
        return ui.value_box(
            "Occupancy",
            f"{pct:.1f}%",
            f"{o['occupied']} of {o['total']} beds",
            theme=color,
        )

    @render.plot
    def icu_trend_plot():
        trend = safe_admissions_trend(days=30)
        if trend.empty:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, "No trend data", ha="center", va="center")
            return fig
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(trend["date"], trend["admissions"], label="Admissions", marker="o", markersize=4)
        if "discharges" in trend.columns:
            ax.plot(trend["date"], trend["discharges"], label="Discharges", marker="s", markersize=4)
        ax.legend()
        ax.set_xlabel("Date")
        ax.set_ylabel("Count")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        return fig

    @render.data_frame
    def readmission_table():
        df = safe_high_readmission(limit=20)
        if df.empty:
            return render.DataGrid(pd.DataFrame({"Message": ["No data"]}), height="200px")
        return render.DataGrid(df.head(20), height="400px")

    @render.data_frame
    def noshow_table():
        df = safe_department_no_show()
        if df.empty:
            return render.DataGrid(pd.DataFrame({"Message": ["No data"]}), height="200px")
        return render.DataGrid(df, height="400px")

    # ---- Patient Twin ----
    @render.ui
    @reactive.event(input.load_twin)
    def twin_demographics():
        pid = input.patient_id()
        if not pid or pid == "":
            return ui.tags.p("Select a patient and click Load.")
        hist = safe_patient_history(pid)
        dem = hist["demographics"]
        if not dem:
            return ui.tags.p("No demographics found for this patient.")
        rows = [ui.tags.tr(ui.tags.td(k), ui.tags.td(str(v))) for k, v in dem.items()]
        return ui.tags.div(
            ui.tags.h5("Demographics"),
            ui.tags.table(ui.tags.tbody(*rows), class_="table table-bordered"),
        )

    @render.data_frame
    @reactive.event(input.load_twin)
    def twin_vitals():
        pid = input.patient_id()
        if not pid or pid == "":
            return render.DataGrid(pd.DataFrame(), height="150px")
        hist = safe_patient_history(pid)
        df = hist["vitals"]
        if df.empty:
            return render.DataGrid(pd.DataFrame({"Message": ["No vitals"]}), height="150px")
        return render.DataGrid(df.head(50), height="200px")

    @render.data_frame
    @reactive.event(input.load_twin)
    def twin_admissions():
        pid = input.patient_id()
        if not pid or pid == "":
            return render.DataGrid(pd.DataFrame(), height="150px")
        hist = safe_patient_history(pid)
        df = hist["admissions"]
        if df.empty:
            return render.DataGrid(pd.DataFrame({"Message": ["No admissions"]}), height="150px")
        return render.DataGrid(df, height="200px")

    @render.data_frame
    @reactive.event(input.load_twin)
    def twin_risk_scores():
        pid = input.patient_id()
        if not pid or pid == "":
            return render.DataGrid(pd.DataFrame(), height="150px")
        hist = safe_patient_history(pid)
        df = hist["risk_scores"]
        if df.empty:
            return render.DataGrid(pd.DataFrame({"Message": ["No risk scores"]}), height="150px")
        return render.DataGrid(df, height="150px")

    @render.ui
    @reactive.event(input.load_twin)
    def twin_ai_explanation():
        pid = input.patient_id()
        if not pid or pid == "":
            return None
        try:
            text = explain_patient_risk(pid)
            return ui.tags.div(
                ui.tags.h5("AI Risk Explanation"),
                ui.tags.p(text),
            )
        except Exception as e:
            return ui.tags.p(f"Explanation unavailable: {e}", style="color: #888;")

    # ---- Trends ----
    @render.plot
    def trend_plot():
        trend = safe_admissions_trend(days=30)
        if trend.empty:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            return fig
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(trend["date"], trend["admissions"], label="Admissions", marker="o", markersize=4)
        if "discharges" in trend.columns:
            ax.plot(trend["date"], trend["discharges"], label="Discharges", marker="s", markersize=4)
        ax.legend()
        ax.set_xlabel("Date")
        ax.set_ylabel("Count")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        return fig

    @render.plot
    def icu_util_plot():
        trend = safe_admissions_trend(days=30)
        if trend.empty:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            return fig
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.fill_between(trend["date"], trend["admissions"], alpha=0.5, label="Admissions")
        ax.plot(trend["date"], trend["admissions"], marker="o", markersize=3)
        ax.set_xlabel("Date")
        ax.set_ylabel("Admissions")
        ax.legend()
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        return fig

    # ---- AI Assistant ----
    @render.ui
    @reactive.event(input.ask_ai)
    def ai_answer():
        q = (input.user_question() or "").strip()
        if not q:
            return ui.tags.p("Enter a question and click Ask AI.")
        try:
            answer = answer_user_question(q)
            return ui.tags.div(
                ui.tags.h5("AI Answer"),
                ui.tags.p(answer),
            )
        except Exception as e:
            return ui.tags.p(f"Error: {e}", style="color: #c00;")


app = App(app_ui, server)
