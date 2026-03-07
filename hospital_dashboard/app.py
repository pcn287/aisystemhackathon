"""
Hospital Operations Command Center — Shiny for Python Dashboard
Dark ops-center theme. Clickable KPIs open modals. All data via safe_* and analytics.
"""

import os
import re
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv

_app_dir = Path(__file__).resolve().parent
for env_path in [Path.cwd() / ".env", _app_dir / ".env", _app_dir.parent / ".env"]:
    if env_path.exists():
        load_dotenv(env_path)
        break
load_dotenv()


def _print_env_diagnostic():
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    print("[hospital_dashboard] Environment diagnostic:")
    print("  SUPABASE_URL:              ", "set" if supabase_url else "NOT SET")
    print("  SUPABASE_SERVICE_ROLE_KEY:  ", "set" if supabase_key else "NOT SET")
    print("  OPENAI_API_KEY:            ", "set" if openai_key else "NOT SET")
    if not supabase_url or not supabase_key:
        print("  -> Supabase vars required. Set them in .env or environment.")
    if not openai_key:
        print("  -> OPENAI_API_KEY optional; AI Assistant disabled without it.")
    print()


_print_env_diagnostic()

import pandas as pd
from shiny import ui, render, reactive, App
from dashboard_log import log as _log, log_error as _log_error

from database_connection import get_admissions, get_icu_beds
from hospital_analytics import (
    compute_icu_occupancy,
    get_high_risk_patients,
    get_no_show_rates,
    get_total_patients,
    get_likely_no_shows,
    get_admissions_trend,
    get_patient_history,
    get_patient_id_list,
    get_system_strain,
)
from hospital_ai_agent import (
    generate_operational_summary,
    explain_patient_risk,
    answer_user_question,
)


def _df(val, fallback=None):
    if val is None or (isinstance(val, pd.DataFrame) and val.empty):
        return fallback if fallback is not None else pd.DataFrame()
    return val


def _records_to_df(records):
    """Convert list of dicts (e.g. from strain) to pandas DataFrame for renderers. Never pass lists to @render.plot or @render.data_frame."""
    if records is None or not isinstance(records, list):
        return pd.DataFrame()
    if not records:
        return pd.DataFrame()
    try:
        return pd.DataFrame(records)
    except Exception:
        return pd.DataFrame()


def safe_total_patients():
    try:
        return get_total_patients()
    except Exception as e:
        _log_error("KPI", "get_total_patients failed", e)
        raise


def safe_icu_occupancy():
    try:
        return compute_icu_occupancy()
    except Exception as e:
        _log_error("KPI", "compute_icu_occupancy failed", e)
        raise


def safe_high_readmission(limit=20):
    try:
        return get_high_risk_patients(limit=limit)
    except Exception as e:
        _log_error("HighRisk", "get_high_risk_patients failed", e)
        raise


def safe_likely_no_shows():
    try:
        return get_likely_no_shows(days_ahead=1)
    except Exception as e:
        _log_error("NoShow", "get_likely_no_shows failed", e)
        raise


def safe_admissions_trend(days=30):
    try:
        return get_admissions_trend(days=days)
    except Exception as e:
        _log_error("Trends", "get_admissions_trend failed", e)
        raise


def safe_department_no_show():
    try:
        return get_no_show_rates()
    except Exception as e:
        _log_error("NoShow", "get_no_show_rates failed", e)
        raise


def safe_patient_history(patient_id):
    try:
        return get_patient_history(patient_id)
    except Exception as e:
        _log_error("PatientTwin", "get_patient_history failed", e)
        raise


def safe_patient_ids():
    try:
        return get_patient_id_list(max_ids=500)
    except Exception as e:
        _log_error("PatientTwin", "get_patient_id_list failed", e)
        raise


def safe_admissions():
    try:
        return get_admissions()
    except Exception as e:
        _log_error("Pipeline", "get_admissions failed", e)
        raise


def safe_icu_beds():
    try:
        return get_icu_beds()
    except Exception as e:
        _log_error("ICU", "get_icu_beds failed", e)
        raise


# Design system — single inline style block
STYLE = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
:root {
  --bg: #0B1120;
  --surface: #131F35;
  --surface2: #1A2942;
  --border: #1E3A5F;
  --primary: #3B82F6;
  --success: #10B981;
  --warning: #F59E0B;
  --danger: #EF4444;
  --text: #F0F6FF;
  --muted: #6B8CAE;
  --mono: 'DM Mono', monospace;
}
body { font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--text); }
.metric-number { font-family: var(--mono); font-size: 2rem; font-weight: 500; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.card-title { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); margin-bottom: 8px; }
.kpi-btn { cursor: pointer; transition: transform 0.15s, border-color 0.15s; }
.kpi-btn:hover { transform: scale(1.02); border-color: var(--primary) !important; }
@keyframes strain-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.85; } }
.strain-pulse { animation: strain-pulse 1.5s ease-in-out infinite; }
.footer-bar { font-size: 0.75rem; color: var(--muted); padding: 8px 16px; border-top: 1px solid var(--border); }
"""


def _safe_html_table(df: pd.DataFrame, max_rows: int = 500) -> str:
    if df is None or df.empty:
        return "<p style='color:var(--muted);'>No data.</p>"
    out = df.head(max_rows).copy()
    out.columns = [str(c) for c in out.columns]
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].astype(str)
    return out.to_html(classes="table table-dark table-hover table-sm", index=False, border=0)


def _safe_date_col(df: pd.DataFrame, candidates: list) -> str | None:
    """Return first existing column name from candidates, or None."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _action_bullets(text: str, max_bullets: int = 4):
    if not text or not str(text).strip():
        return [("💡", "No summary available.")]
    t = str(text).strip()
    bullets = []
    for sent in re.split(r"[.\n]+", t):
        sent = sent.strip()
        if len(sent) < 12:
            continue
        lower = sent.lower()
        if re.search(r"escalat|critical|immediate|urgent", lower):
            bullets.append(("🚨", sent[:200]))
        elif re.search(r"monitor|caution|elevated|watch", lower):
            bullets.append(("⚠️", sent[:200]))
        elif re.search(r"normal|stable|within|adequate|no immediate", lower):
            bullets.append(("✅", sent[:200]))
        else:
            bullets.append(("💡", sent[:200]))
        if len(bullets) >= max_bullets:
            break
    if not bullets:
        bullets = [("💡", t[:200] + ("..." if len(t) > 200 else ""))]
    return bullets[:max_bullets]


# ═══════════════════════════════════════
# APP UI
# ═══════════════════════════════════════
app_ui = ui.page_fluid(
    ui.tags.head(ui.tags.title("Hospital Operations Command Center"), ui.tags.style(STYLE)),
    ui.tags.div(
        id="page_loading_bar",
        style=(
            "position: fixed; top: 0; left: 0; right: 0; height: 3px; "
            "background: linear-gradient(90deg, #3B82F6 0%, #0EA5E9 50%, #3B82F6 100%); "
            "background-size: 200% 100%; animation: loading_bar 1.5s infinite; z-index: 9999; display: none;"
        ),
    ),
    ui.tags.style(
        "@keyframes loading_bar { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }"
    ),
    ui.tags.div(
        {"class": "hd-dashboard", "style": "min-height:100vh; background:var(--bg); color:var(--text);"},
        ui.page_navbar(
            # Tab 1: Command Center
            ui.nav_panel(
                "Command Center",
                ui.output_ui("health_banner"),
                ui.layout_columns(
                    ui.output_ui("kpi_total_wrap"),
                    ui.output_ui("kpi_icu_wrap"),
                    ui.output_ui("kpi_readmit_wrap"),
                    ui.output_ui("kpi_noshow_wrap"),
                    col_widths=(3, 3, 3, 3),
                    gap="12px",
                ),
                ui.layout_columns(
                    ui.output_plot("gauge_icu"),
                    ui.output_plot("gauge_readmit"),
                    ui.output_plot("gauge_noshow"),
                    col_widths=(4, 4, 4),
                ),
                ui.output_ui("icu_bed_grid"),
                ui.output_ui("alerts_feed"),
                ui.input_action_button("refresh_ai", "Refresh AI Brief", class_="btn-primary", style="margin-bottom: 8px;"),
                ui.output_ui("cmd_action_items"),
                ui.output_ui("discharge_pipeline"),
                ui.output_ui("department_breakdown"),
            ),
            # Tab 2: ICU Capacity (unique output IDs to avoid duplicate-ID conflicts)
            ui.nav_panel(
                "ICU Capacity",
                ui.layout_sidebar(
                    ui.sidebar(
                        ui.input_select("icu_days_range", "Trend Range", choices={"7": "7 days", "14": "2 weeks", "30": "30 days"}, selected="30"),
                        ui.input_select("icu_chart_type", "Chart Type", choices={"line": "Line", "area": "Area", "bar": "Bar"}, selected="area"),
                        title="Controls",
                        width="200px",
                    ),
                    ui.output_plot("gauge_icu_tab2"),
                    ui.output_plot("icu_trend_plot"),
                    ui.output_ui("icu_bed_grid_tab2"),
                    ui.output_ui("icu_stats_cards"),
                ),
            ),
            # Tab 3: High Readmission Risk
            ui.nav_panel(
                "High Readmission Risk",
                ui.output_ui("readmission_summary_bar"),
                ui.layout_columns(
                    ui.input_select("risk_sort", "Sort by", choices={"risk": "Risk Score", "admissions": "Admissions", "id": "Patient ID"}, selected="risk"),
                    ui.input_select("risk_filter", "Filter", choices={"all": "All", "critical": "Critical only (≥80%)", "high": "High (60-80%)"}, selected="all"),
                    col_widths=(4, 4),
                ),
                ui.layout_columns(
                    ui.input_select("readmission_view_patient", "View full history for patient", choices={}, selected=None),
                    ui.input_action_button("readmission_view_btn", "View full history"),
                    col_widths=(6, 2),
                ),
                ui.output_ui("readmission_cards"),
                ui.output_plot("readmission_dist_plot"),
            ),
            # Tab 4: No-Show Risk
            ui.nav_panel(
                "No-Show Risk",
                ui.output_ui("noshow_summary_row"),
                ui.layout_columns(
                    ui.output_plot("noshow_bar_plot"),
                    ui.output_ui("noshow_stats"),
                    col_widths=(6, 4),
                ),
                ui.output_ui("noshow_patients_table_wrap"),
            ),
            # Tab 5: Patient Twin
            ui.nav_panel(
                "Patient Twin",
                ui.layout_sidebar(
                    ui.sidebar(
                        ui.input_select("patient_id", "Patient", choices={"": "Select..."}, selected=""),
                        ui.input_action_button("load_twin", "Load Twin", class_="btn-primary"),
                        ui.output_ui("twin_mini_badge"),
                        title="Patient",
                        width="240px",
                    ),
                    ui.output_ui("twin_demographics"),
                    ui.output_plot("twin_vitals_plot"),
                    ui.output_plot("twin_admissions_plot"),
                    ui.output_ui("twin_risk_chips"),
                    ui.output_ui("twin_ai_explanation"),
                ),
            ),
            # Tab 6: Trends
            ui.nav_panel(
                "Trends",
                ui.layout_columns(
                    ui.input_date_range("trend_date_range", "Date Range", start=(datetime.now() - timedelta(days=30)).date(), end=datetime.now().date()),
                    ui.input_select("trend_metric", "Metric", choices={"admissions": "Admissions", "discharges": "Discharges", "both": "Both"}, selected="both"),
                    ui.input_checkbox("show_ma", "Show 7-day moving average", value=True),
                    col_widths=(4, 4, 4),
                ),
                ui.output_plot("trend_main_plot"),
                ui.output_plot("trend_net_plot"),
                ui.output_ui("trend_stats"),
            ),
            # Tab 7: AI Assistant
            ui.nav_panel(
                "AI Assistant",
                ui.tags.div(
                    ui.input_action_button("btn_q1", "🏥 Who needs attention today?", class_="kpi-btn", style="margin:4px;"),
                    ui.input_action_button("btn_q2", "📈 ICU forecast tomorrow", class_="kpi-btn", style="margin:4px;"),
                    ui.input_action_button("btn_q3", "📅 Worst no-show departments", class_="kpi-btn", style="margin:4px;"),
                    ui.input_action_button("btn_q4", "⚡ Summarize readmission trends", class_="kpi-btn", style="margin:4px;"),
                    style="margin-bottom:12px;",
                ),
                ui.input_text_area("user_question", "Question", rows=3, placeholder="Ask about patients, ICU, no-shows..."),
                ui.layout_columns(
                    ui.input_action_button("ask_ai", "Ask AI", class_="btn-primary"),
                    ui.input_action_button("clear_chat", "Clear"),
                    col_widths=(2, 2),
                ),
                ui.output_ui("ai_answer"),
            ),
            title=ui.tags.span("Hospital Operations Command Center", style="font-weight:700;"),
            id="main_nav",
            selected="Command Center",
            navbar_options=ui.navbar_options(position="static-top"),
        ),
        ui.tags.div(ui.output_ui("footer_bar"), class_="footer-bar"),
    ),
)


def server(input, output, session):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    def _style_ax(ax, fig):
        ax.set_facecolor("#F8FAFC")
        fig.patch.set_facecolor("#FFFFFF")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#E2E8F0")
        ax.spines["left"].set_color("#E2E8F0")
        ax.tick_params(colors="#64748B", labelsize=9)
        ax.xaxis.label.set_color("#64748B")
        ax.yaxis.label.set_color("#64748B")
        ax.grid(True, axis="y", color="#E2E8F0", linestyle="--", alpha=0.7)
        fig.tight_layout()

    # Cached strain: computed once, reused by all dependents (avoids repeated DB/analytics)
    strain_cache = reactive.Value(None)

    # Pre-warm cache on first session so UI renders instantly
    @reactive.effect
    def _warm_cache():
        from database_connection import DATA_CACHE
        t = threading.Thread(target=DATA_CACHE.warm, daemon=True)
        t.start()

    last_refresh = reactive.Value(datetime.now().strftime("%Y-%m-%d %H:%M"))

    # Only time-series charts depend on _tick (refresh every minute); no reactive.calc should use it
    @reactive.poll(lambda: int(time.time() // 60), interval_secs=60)
    def _tick():
        return int(time.time() // 60)

    # ─── Modal helper ─────────────────────────────────────────────────────
    def show_patient_modal(title: str, df: pd.DataFrame, session):
        if df is None or df.empty:
            content = ui.tags.p("No patients to display.", style="color: var(--muted);")
        else:
            content = ui.tags.div(
                ui.tags.p(f"{len(df)} patients", style="color:var(--muted); font-size:0.85rem; margin-bottom:12px;"),
                ui.HTML(_safe_html_table(df)),
            )
        ui.modal_show(
            ui.modal(
                ui.modal_header(title),
                ui.modal_body(content),
                ui.modal_footer(ui.modal_button("Close")),
                size="xl",
                easy_close=True,
            ),
            session=session,
        )

    # ─── Error helpers for render/calc ────────────────────────────────────
    def _render_err(name: str, e: Exception):
        import traceback
        traceback.print_exc()
        return ui.tags.div(f"ERROR in {name}: {e}", style="color:red; padding:10px; font-size:12px;")

    def _placeholder_plot(name: str, msg: str = "No data available"):
        """Return a placeholder matplotlib figure so the UI never spins. Logs fallback."""
        _log("Render", f"fallback placeholder plot: {name}", reason=msg)
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, msg, ha="center", va="center", transform=ax.transAxes, color="#64748B", fontsize=13)
        ax.set_axis_off()
        fig.patch.set_facecolor("#FFFFFF")
        fig.tight_layout()
        return fig

    _STRAIN_FALLBACK = {
        "icu_rate": 0.0, "readmit_rate": 0.0, "noshow_rate": 0.0,
        "strain_score": 0.0, "strain_level": "unknown",
        "total_patients": 0, "icu_total": 50, "icu_occupied": 0,
        "high_readmission_count": 0, "likely_no_show_count": 0,
        "admissions_today": 0, "discharges_today": 0, "discharge_pending": 0,
        "admissions_trend_records": [], "department_no_show_records": [],
        "data_as_of": "unavailable",
    }

    # ─── KPI previous values for trend arrows ─────────────────────────────
    kpi_prev = reactive.Value({"total": None, "icu_pct": None, "readmit": None, "noshow": None})

    @reactive.calc
    def kpi_current():
        try:
            s = r_strain()
            total = s.get("total_patients", 0) or 0
            icu_pct = (s.get("icu_rate") or 0) * 100
            readmit = s.get("high_readmission_count", 0) or 0
            noshow = s.get("likely_no_show_count", 0) or 0
            return {"total": total, "icu_pct": icu_pct, "readmit": readmit, "noshow": noshow}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"total": 0, "icu_pct": 0, "readmit": 0, "noshow": 0}

    @reactive.effect
    def _kpi_prev_update():
        c = kpi_current()
        kpi_prev.set(c)

    def _trend_arrow(name: str, curr, prev_val, bad_metric: bool):
        if prev_val is None:
            return "→", "var(--muted)"
        if curr > prev_val:
            return "↑", "#EF4444" if bad_metric else "var(--muted)"
        if curr < prev_val:
            return "↓", "#10B981" if bad_metric else "var(--muted)"
        return "→", "var(--muted)"

    # ─── Reactive calcs (r_* style); strain is cached to avoid repeated DB/analytics ───
    @reactive.calc
    def r_strain():
        """Single source of truth for Command Center KPIs and AI context. Cached so get_system_strain() runs once."""
        cached = strain_cache.get()
        if cached is not None:
            return cached
        try:
            data = get_system_strain()
            strain_cache.set(data)
            return data
        except Exception as e:
            import traceback
            traceback.print_exc()
            _log_error("Strain", "get_system_strain failed", e)
            return dict(_STRAIN_FALLBACK)

    @reactive.calc
    def r_strain_trend_df():
        """Trend data from strain as a DataFrame for plots/tables. Never pass lists to renderers."""
        try:
            s = r_strain()
            return _records_to_df(s.get("admissions_trend_records"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @reactive.calc
    def r_strain_dept_no_show_df():
        """Department no-show data from strain as a DataFrame for plots/tables. Never pass lists to renderers."""
        try:
            s = r_strain()
            return _records_to_df(s.get("department_no_show_records"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @reactive.calc
    def r_icu():
        try:
            s = r_strain()
            return {
                "total": s.get("icu_total", 0),
                "occupied": s.get("icu_occupied", 0),
                "rate": s.get("icu_rate", 0.0),
                "high_operational_risk": (s.get("icu_rate") or 0) >= 0.9,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"total": 50, "occupied": 0, "rate": 0.0, "high_operational_risk": False}

    @reactive.calc
    def r_icu_beds_df():
        try:
            return safe_icu_beds()
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @reactive.calc
    def r_trend():
        try:
            days = 30
            if hasattr(input, "icu_days_range") and input.icu_days_range() is not None:
                try:
                    days = int(input.icu_days_range())
                except Exception:
                    pass
            return safe_admissions_trend(days=days)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @reactive.calc
    def r_admissions():
        try:
            return safe_admissions()
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @reactive.calc
    def r_high_risk_500():
        try:
            return safe_high_readmission(limit=500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @reactive.calc
    def r_trend_60():
        try:
            return safe_admissions_trend(days=60)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @reactive.calc
    def readmission_data():
        try:
            df = safe_high_readmission(limit=100)
            return (df, None) if df is not None and not df.empty else (pd.DataFrame(), None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            _log_error("Shiny", "readmission_data failed", e)
            return (pd.DataFrame(), str(e))

    @reactive.calc
    def noshow_data():
        try:
            df = get_no_show_rates()
            return (df, None) if df is not None and not df.empty else (pd.DataFrame(), None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            _log_error("Shiny", "noshow_data failed", e)
            return (pd.DataFrame(), str(e))

    @reactive.calc
    def r_likely_no_shows():
        try:
            return safe_likely_no_shows()
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @reactive.calc
    def r_dept_breakdown():
        try:
            try:
                dept_rates = safe_department_no_show()
            except Exception:
                dept_rates = pd.DataFrame()
            high_risk = r_high_risk_500()
            beds_df = r_icu_beds_df()
            adm_df = r_admissions()
            return {"dept_rates": dept_rates, "high_risk": high_risk, "beds_df": beds_df, "adm_df": adm_df}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"dept_rates": pd.DataFrame(), "high_risk": pd.DataFrame(), "beds_df": pd.DataFrame(), "adm_df": pd.DataFrame()}

    @reactive.calc
    def r_patient_ids():
        """Patient ID list for dropdown and modals; not invalidated by _tick."""
        try:
            return safe_patient_ids() or []
        except Exception as e:
            _log_error("Shiny", "r_patient_ids failed", e)
            return []

    @reactive.calc
    def r_patient_history():
        """Patient twin history for current selection; depends only on input.patient_id()."""
        try:
            pid = input.patient_id() if hasattr(input, "patient_id") else None
            if not pid or not str(pid).strip():
                return {}
            return safe_patient_history(str(pid).strip()) or {}
        except Exception as e:
            _log_error("Shiny", "r_patient_history failed", e)
            return {}

    @reactive.calc
    def r_discharge_pipeline():
        """Returns (ready_today_df, overdue_df, long_stay_df) from admissions."""
        try:
            df = r_admissions()
            if df is None or df.empty:
                return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
            adate = _safe_date_col(df, ["admission_date", "admit_date", "start_date", "date"])
            ddate = _safe_date_col(df, ["discharge_date", "discharge_at", "end_date"])
            expdate = _safe_date_col(df, ["expected_discharge_date", "expected_discharge", "planned_discharge"])
            if not adate:
                return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
            df = df.copy()
            df[adate] = pd.to_datetime(df[adate], errors="coerce")
            df = df.dropna(subset=[adate])
            ref = df[adate].max()
            today = ref.date() if not pd.isna(ref) else pd.Timestamp.now().normalize().date()
            if ddate:
                df[ddate] = pd.to_datetime(df[ddate], errors="coerce")
                still_present = df[ddate].isna() | (df[ddate].dt.date > today)
            else:
                still_present = pd.Series(True, index=df.index)
            use_exp = expdate if expdate and expdate in df.columns else ddate
            if use_exp and use_exp in df.columns:
                df[use_exp] = pd.to_datetime(df[use_exp], errors="coerce")
            else:
                use_exp = None
            if use_exp:
                ready = still_present & (df[use_exp].dt.date == today)
            else:
                ready = pd.Series(False, index=df.index)
            ready_df = df.loc[ready].copy()
            if use_exp:
                overdue = still_present & df[use_exp].notna() & (df[use_exp].dt.date < today)
            else:
                overdue = pd.Series(False, index=df.index)
            overdue_df = df.loc[overdue].copy()
            cutoff = today - timedelta(days=7)
            long_stay = still_present & (df[adate].dt.date < cutoff)
            long_stay_df = df.loc[long_stay].copy()
            return (ready_df, overdue_df, long_stay_df)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    # ─── Command Center: Health Banner ────────────────────────────────────
    @render.ui
    def health_banner():
        try:
            s = r_strain()
            strain = s.get("strain_score", 0) or 0
            icu_rate = (s.get("icu_rate") or 0) * 100
            readmit_rate = (s.get("readmit_rate") or 0) * 100
            noshow_rate = (s.get("noshow_rate") or 0) * 100
            if strain < 40:
                bg = "#10B981"
                msg = "SYSTEM OPERATING NORMALLY"
            elif strain <= 70:
                bg = "#F59E0B"
                msg = "ELEVATED STRAIN — MONITOR CLOSELY"
            else:
                bg = "#EF4444"
                msg = "HIGH STRAIN — ACTION REQUIRED"
            pulse_class = " strain-pulse" if strain > 70 else ""
            return ui.tags.div(
                ui.tags.div(
                    ui.tags.span("Strain Score: ", style="font-family: var(--mono); font-size: 1rem;"),
                    ui.tags.span(f"{strain:.0f} / 100", style="font-family: var(--mono); font-size: 1.25rem; font-weight: 600;"),
                    style="margin-bottom: 8px;",
                ),
                ui.tags.div(msg, style="font-weight: 700; font-size: 1.1rem; margin-bottom: 8px;"),
                ui.tags.div(
                    ui.tags.span(f"ICU: {icu_rate:.0f}%", style="background: rgba(0,0,0,0.2); padding: 4px 10px; border-radius: 20px; margin-right: 8px; font-size: 0.85rem;"),
                    ui.tags.span(f"Readmit: {readmit_rate:.1f}%", style="background: rgba(0,0,0,0.2); padding: 4px 10px; border-radius: 20px; margin-right: 8px; font-size: 0.85rem;"),
                    ui.tags.span(f"No-Show: {noshow_rate:.1f}%", style="background: rgba(0,0,0,0.2); padding: 4px 10px; border-radius: 20px; font-size: 0.85rem;"),
                ),
                style=f"background: {bg}; color: #fff; padding: 20px; border-radius: 12px; margin-bottom: 20px;{pulse_class}",
            )
        except Exception as e:
            return _render_err("health_banner", e)

    # ─── KPI cards (clickable) ───────────────────────────────────────────
    @render.ui
    def kpi_total_wrap():
        try:
            cur = kpi_current()
            prev = kpi_prev()
            n = cur["total"]
            arrow, arrow_color = _trend_arrow("total", n, prev.get("total") if isinstance(prev, dict) else None, False)
            return ui.input_action_button(
                "btn_kpi_total",
                ui.tags.div(
                    ui.tags.div("Total Patients", class_="card-title"),
                    ui.tags.div(str(n), class_="metric-number"),
                    ui.tags.div(ui.tags.span("Census", style="margin-right: 6px;"), ui.tags.span(arrow, style=f"color: {arrow_color}; font-weight: 700;"), style="font-size: 0.8rem; color: var(--muted); margin-top: 4px;"),
                ),
                style="width:100%; text-align:left; background: var(--surface); border: 2px solid var(--border); border-radius: 12px; padding: 20px; cursor: pointer;",
                class_="kpi-btn",
            )
        except Exception as e:
            return _render_err("kpi_total_wrap", e)

    @reactive.effect
    @reactive.event(input.btn_kpi_total)
    def _modal_kpi_total():
        try:
            ids = r_patient_ids()
            df = pd.DataFrame({"Patient ID": ids}) if ids else pd.DataFrame()
        except Exception:
            df = pd.DataFrame()
        show_patient_modal("Total Patients", df, session)

    @render.ui
    def kpi_icu_wrap():
        try:
            cur = kpi_current()
            prev = kpi_prev()
            o = r_icu()
            pct = cur["icu_pct"]
            total = o.get("total") or 0
            occ = o.get("occupied") or 0
            arrow, arrow_color = _trend_arrow("icu", pct, prev.get("icu_pct") if isinstance(prev, dict) else None, True)
            return ui.input_action_button(
                "btn_kpi_icu",
                ui.tags.div(
                    ui.tags.div("ICU Occupancy", class_="card-title"),
                    ui.tags.div(f"{occ} / {total} ({pct:.0f}%)", class_="metric-number"),
                    ui.tags.div(ui.tags.span(f"{pct:.1f}%", style="margin-right: 6px;"), ui.tags.span(arrow, style=f"color: {arrow_color}; font-weight: 700;"), style="font-size: 0.8rem; color: var(--muted); margin-top: 4px;"),
                ),
                style="width:100%; text-align:left; background: var(--surface); border: 2px solid var(--border); border-radius: 12px; padding: 20px; cursor: pointer;",
                class_="kpi-btn",
            )
        except Exception as e:
            return _render_err("kpi_icu_wrap", e)

    @reactive.effect
    @reactive.event(input.btn_kpi_icu)
    def _modal_kpi_icu():
        o = r_icu()
        df = pd.DataFrame([{"Total Beds": o.get("total", 0), "Occupied": o.get("occupied", 0), "Free": (o.get("total") or 0) - (o.get("occupied") or 0), "Rate %": f"{(o.get('rate') or 0)*100:.1f}"}])
        show_patient_modal("ICU Capacity Summary", df, session)

    @render.ui
    def kpi_readmit_wrap():
        try:
            cur = kpi_current()
            prev = kpi_prev()
            n = cur["readmit"]
            arrow, arrow_color = _trend_arrow("readmit", n, prev.get("readmit") if isinstance(prev, dict) else None, True)
            return ui.input_action_button(
                "btn_kpi_readmit",
                ui.tags.div(
                    ui.tags.div("High Readmission Risk", class_="card-title"),
                    ui.tags.div(str(n), class_="metric-number"),
                    ui.tags.div(ui.tags.span("Patients ≥60%", style="margin-right: 6px;"), ui.tags.span(arrow, style=f"color: {arrow_color}; font-weight: 700;"), style="font-size: 0.8rem; color: var(--muted); margin-top: 4px;"),
                    ui.tags.div("Source: risk_scores table, threshold ≥ 0.6", style="font-size: 0.65rem; color: var(--muted); margin-top: 4px;"),
                ),
                style="width:100%; text-align:left; background: var(--surface); border: 2px solid var(--border); border-radius: 12px; padding: 20px; cursor: pointer;",
                class_="kpi-btn",
            )
        except Exception as e:
            return _render_err("kpi_readmit_wrap", e)

    @reactive.effect
    @reactive.event(input.btn_kpi_readmit)
    def _modal_kpi_readmit():
        df = r_high_risk_500()
        show_patient_modal("High Readmission Risk Patients", df, session)

    @render.ui
    def kpi_noshow_wrap():
        try:
            cur = kpi_current()
            prev = kpi_prev()
            n = cur["noshow"]
            arrow, arrow_color = _trend_arrow("noshow", n, prev.get("noshow") if isinstance(prev, dict) else None, True)
            return ui.input_action_button(
                "btn_kpi_noshow",
                ui.tags.div(
                    ui.tags.div("Likely No-Shows Tomorrow", class_="card-title"),
                    ui.tags.div(str(n), class_="metric-number"),
                    ui.tags.div(ui.tags.span("Appointments", style="margin-right: 6px;"), ui.tags.span(arrow, style=f"color: {arrow_color}; font-weight: 700;"), style="font-size: 0.8rem; color: var(--muted); margin-top: 4px;"),
                ),
                style="width:100%; text-align:left; background: var(--surface); border: 2px solid var(--border); border-radius: 12px; padding: 20px; cursor: pointer;",
                class_="kpi-btn",
            )
        except Exception as e:
            return _render_err("kpi_noshow_wrap", e)

    @reactive.effect
    @reactive.event(input.btn_kpi_noshow)
    def _modal_kpi_noshow():
        try:
            df = r_likely_no_shows()
        except Exception:
            df = pd.DataFrame()
        show_patient_modal("Likely No-Show Appointments", df, session)

    # ─── Gauges (matplotlib) ──────────────────────────────────────────────
    @render.plot
    def gauge_icu():
        try:
            s = r_strain()
            pct = s.get("icu_rate", 0) * 100
            fig, ax = plt.subplots(figsize=(4, 2.5), subplot_kw=dict(polar=False))
            color = "#DC2626" if pct >= 90 else "#D97706" if pct >= 70 else "#0D9373"
            ax.set_facecolor("#F8FAFC")
            fig.patch.set_facecolor("#FFFFFF")
            ax.barh(0, pct, color=color, height=0.4, left=0, zorder=3)
            ax.barh(0, 100, color="#E2E8F0", height=0.4, left=0, zorder=2)
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            ax.set_xlabel("ICU Occupancy %", color="#64748B", fontsize=10)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.axvline(x=90, color="#DC2626", linestyle="--", alpha=0.5, linewidth=1, label="Critical 90%")
            ax.axvline(x=70, color="#D97706", linestyle="--", alpha=0.5, linewidth=1, label="Caution 70%")
            ax.text(pct / 2, 0, f"{pct:.1f}%", ha="center", va="center", fontsize=14, fontweight="bold", color="white", zorder=4)
            occupied = s.get("icu_occupied", 0)
            total = s.get("icu_total", 50)
            ax.set_title(f"ICU: {occupied}/{total} beds occupied", color="#1E293B", fontsize=11, pad=10)
            fig.tight_layout()
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("gauge_icu", f"Error: {e}")

    @render.plot
    def gauge_icu_tab2():
        try:
            s = r_strain()
            pct = s.get("icu_rate", 0) * 100
            fig, ax = plt.subplots(figsize=(4, 2.5), subplot_kw=dict(polar=False))
            color = "#DC2626" if pct >= 90 else "#D97706" if pct >= 70 else "#0D9373"
            ax.set_facecolor("#F8FAFC")
            fig.patch.set_facecolor("#FFFFFF")
            ax.barh(0, pct, color=color, height=0.4, left=0, zorder=3)
            ax.barh(0, 100, color="#E2E8F0", height=0.4, left=0, zorder=2)
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            ax.set_xlabel("ICU Occupancy %", color="#64748B", fontsize=10)
            for spine in ax.spines.values():
                spine.set_visible(False)
            occupied = s.get("icu_occupied", 0)
            total = s.get("icu_total", 50)
            ax.set_title(f"ICU: {occupied}/{total} beds occupied", color="#1E293B", fontsize=11, pad=10)
            fig.tight_layout()
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("gauge_icu_tab2", f"Error: {e}")

    @render.plot
    def gauge_readmit():
        try:
            s = r_strain()
            total = max(1, s.get("total_patients", 0) or 1)
            high = s.get("high_readmission_count", 0) or 0
            pct = min(100, (high / total) * 100)
            fig, ax = plt.subplots(figsize=(4, 2.5), subplot_kw=dict(polar=False))
            color = "#DC2626" if pct >= 15 else "#D97706" if pct >= 5 else "#0D9373"
            ax.set_facecolor("#F8FAFC")
            fig.patch.set_facecolor("#FFFFFF")
            ax.barh(0, pct, color=color, height=0.4, left=0, zorder=3)
            ax.barh(0, 100, color="#E2E8F0", height=0.4, left=0, zorder=2)
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            ax.set_xlabel("Readmission Pressure %", color="#64748B", fontsize=10)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.set_title(f"High risk: {high} patients", color="#1E293B", fontsize=11, pad=10)
            fig.tight_layout()
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("gauge_readmit", f"Error: {e}")

    @render.plot
    def gauge_noshow():
        try:
            s = r_strain()
            total = max(1, s.get("total_patients", 0) or 1)
            noshow = s.get("likely_no_show_count", 0) or 0
            noshow_pct = min(100, (noshow / max(total * 0.1, 1)) * 100)
            reliability = 100 - noshow_pct
            fig, ax = plt.subplots(figsize=(4, 2.5), subplot_kw=dict(polar=False))
            color = "#DC2626" if reliability < 75 else "#D97706" if reliability < 90 else "#0D9373"
            ax.set_facecolor("#F8FAFC")
            fig.patch.set_facecolor("#FFFFFF")
            ax.barh(0, reliability, color=color, height=0.4, left=0, zorder=3)
            ax.barh(0, 100, color="#E2E8F0", height=0.4, left=0, zorder=2)
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            ax.set_xlabel("Appt Reliability %", color="#64748B", fontsize=10)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.set_title(f"Likely no-shows: {noshow}", color="#1E293B", fontsize=11, pad=10)
            fig.tight_layout()
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("gauge_noshow", f"Error: {e}")

    # ─── ICU Bed Grid ─────────────────────────────────────────────────────
    _bed_click_prev = reactive.Value({})

    @render.ui
    def icu_bed_grid():
        try:
            o = r_icu()
            beds_df = r_icu_beds_df()
            total = max(1, min(50, o.get("total") or 50, len(beds_df) if not beds_df.empty else 50))
            occupied = min(o.get("occupied") or 0, total)
            cells = []
            for i in range(total):
                is_occ = i < occupied
                color = "#EF4444" if is_occ else "#10B981"
                cells.append(ui.input_action_button(f"bed_{i}", ui.tags.div(style=f"width:36px;height:36px;border-radius:6px;background:{color};"), style="padding:0; border:none; cursor:pointer; min-width:36px; min-height:36px;"))
            grid = ui.tags.div(*cells, style="display:grid; grid-template-columns: repeat(10, 36px); gap: 6px; max-width: 420px;")
            return ui.tags.div(
                ui.tags.p("ICU Beds (click for detail)", style="font-size: 0.85rem; color: var(--muted); margin-bottom: 8px;"),
                grid,
                ui.tags.p("● Occupied  ● Free", style="font-size: 0.75rem; color: var(--muted); margin-top: 8px;"),
                style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px;",
            )
        except Exception as e:
            return _render_err("icu_bed_grid", e)

    _bed_click_prev_tab2 = reactive.Value({})

    @render.ui
    def icu_bed_grid_tab2():
        try:
            o = r_icu()
            beds_df = r_icu_beds_df()
            total = max(1, min(50, o.get("total") or 50, len(beds_df) if not beds_df.empty else 50))
            occupied = min(o.get("occupied") or 0, total)
            cells = []
            for i in range(total):
                is_occ = i < occupied
                color = "#EF4444" if is_occ else "#10B981"
                cells.append(ui.input_action_button(f"bed_t2_{i}", ui.tags.div(style=f"width:36px;height:36px;border-radius:6px;background:{color};"), style="padding:0; border:none; cursor:pointer; min-width:36px; min-height:36px;"))
            grid = ui.tags.div(*cells, style="display:grid; grid-template-columns: repeat(10, 36px); gap: 6px; max-width: 420px;")
            return ui.tags.div(
                ui.tags.p("ICU Beds (click for detail)", style="font-size: 0.85rem; color: var(--muted); margin-bottom: 8px;"),
                grid,
                ui.tags.p("● Occupied  ● Free", style="font-size: 0.75rem; color: var(--muted); margin-top: 8px;"),
                style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px;",
            )
        except Exception as e:
            return _render_err("icu_bed_grid_tab2", e)

    @reactive.Effect
    def _icu_bed_click_modal():
        try:
            beds_df = r_icu_beds_df()
            o = r_icu()
            total = max(1, min(50, o.get("total") or 50, len(beds_df) if not beds_df.empty else 50))
            prev = _bed_click_prev()
            if not isinstance(prev, dict):
                prev = {}
            clicks = {}
            for i in range(total):
                try:
                    clicks[i] = input[f"bed_{i}"]()
                except Exception:
                    clicks[i] = 0
            for i in range(total):
                try:
                    if clicks.get(i, 0) > prev.get(i, 0):
                        _bed_click_prev.set(clicks)
                        if beds_df is not None and not beds_df.empty and i < len(beds_df):
                            row = beds_df.iloc[i]
                            pid_col = next((c for c in beds_df.columns if "patient" in c.lower()), None)
                            adate_col = next((c for c in beds_df.columns if "admission" in c.lower() or "date" in c.lower()), None)
                            occupied = pid_col and pd.notna(row.get(pid_col)) and str(row.get(pid_col)).strip() not in ("", "nan", "None")
                            if not occupied and "status" in beds_df.columns:
                                occupied = str(row.get("status", "")).lower() in ("true", "1", "occupied", "yes")
                            if not occupied and "occupied" in beds_df.columns:
                                occupied = row.get("occupied") in (True, 1, "true", "1", "yes")
                            if occupied and pid_col:
                                pid = row.get(pid_col, "—")
                                adate = row.get(adate_col, None) if adate_col else None
                                if adate is not None and pd.notna(adate):
                                    try:
                                        ad = pd.to_datetime(adate)
                                        days = (pd.Timestamp.now().normalize() - ad.normalize()).days
                                        days_str = f"{days} days in ICU"
                                    except Exception:
                                        days_str = str(adate)
                                else:
                                    days_str = "—"
                                body = ui.tags.div(
                                    ui.tags.p(ui.tags.strong("Patient ID: "), str(pid)),
                                    ui.tags.p(ui.tags.strong("Admission date: "), str(adate) if adate is not None else "—"),
                                    ui.tags.p(ui.tags.strong("Days in ICU: "), days_str),
                                )
                            else:
                                body = ui.tags.p(f"Bed {i} — Available", style="color: var(--muted);")
                        else:
                            body = ui.tags.p(f"Bed {i} — Available", style="color: var(--muted);")
                        ui.modal_show(ui.modal(ui.modal_header(f"Bed {i}"), ui.modal_body(body), ui.modal_footer(ui.modal_button("Close")), size="s", easy_close=True), session=session)
                        return
                except Exception:
                    pass
            _bed_click_prev.set(clicks)
        except Exception:
            pass

    @reactive.Effect
    def _icu_bed_click_modal_tab2():
        try:
            beds_df = r_icu_beds_df()
            o = r_icu()
            total = max(1, min(50, o.get("total") or 50, len(beds_df) if not beds_df.empty else 50))
            prev = _bed_click_prev_tab2()
            if not isinstance(prev, dict):
                prev = {}
            clicks = {}
            for i in range(total):
                try:
                    clicks[i] = input[f"bed_t2_{i}"]()
                except Exception:
                    clicks[i] = 0
            for i in range(total):
                try:
                    if clicks.get(i, 0) > prev.get(i, 0):
                        _bed_click_prev_tab2.set(clicks)
                        if beds_df is not None and not beds_df.empty and i < len(beds_df):
                            row = beds_df.iloc[i]
                            pid_col = next((c for c in beds_df.columns if "patient" in c.lower()), None)
                            adate_col = next((c for c in beds_df.columns if "admission" in c.lower() or "date" in c.lower()), None)
                            occupied = pid_col and pd.notna(row.get(pid_col)) and str(row.get(pid_col)).strip() not in ("", "nan", "None")
                            if not occupied and "status" in beds_df.columns:
                                occupied = str(row.get("status", "")).lower() in ("true", "1", "occupied", "yes")
                            if not occupied and "occupied" in beds_df.columns:
                                occupied = row.get("occupied") in (True, 1, "true", "1", "yes")
                            if occupied and pid_col:
                                pid = row.get(pid_col, "—")
                                adate = row.get(adate_col, None) if adate_col else None
                                if adate is not None and pd.notna(adate):
                                    try:
                                        ad = pd.to_datetime(adate)
                                        days = (pd.Timestamp.now().normalize() - ad.normalize()).days
                                        days_str = f"{days} days in ICU"
                                    except Exception:
                                        days_str = str(adate)
                                else:
                                    days_str = "—"
                                body = ui.tags.div(
                                    ui.tags.p(ui.tags.strong("Patient ID: "), str(pid)),
                                    ui.tags.p(ui.tags.strong("Admission date: "), str(adate) if adate is not None else "—"),
                                    ui.tags.p(ui.tags.strong("Days in ICU: "), days_str),
                                )
                            else:
                                body = ui.tags.p(f"Bed {i} — Available", style="color: var(--muted);")
                        else:
                            body = ui.tags.p(f"Bed {i} — Available", style="color: var(--muted);")
                        ui.modal_show(ui.modal(ui.modal_header(f"Bed {i}"), ui.modal_body(body), ui.modal_footer(ui.modal_button("Close")), size="s", easy_close=True), session=session)
                        return
                except Exception:
                    pass
            _bed_click_prev_tab2.set(clicks)
        except Exception:
            pass

    # ─── Alerts Feed ──────────────────────────────────────────────────────
    @render.ui
    def alerts_feed():
        try:
            s = r_strain()
            alerts = []
            if (s.get("icu_rate") or 0) * 100 >= 90:
                alerts.append(("#EF4444", "ICU occupancy ≥ 90%", datetime.now().strftime("%H:%M")))
            elif (s.get("icu_rate") or 0) * 100 >= 70:
                alerts.append(("#F59E0B", "ICU occupancy elevated", datetime.now().strftime("%H:%M")))
            n = s.get("high_readmission_count", 0) or 0
            if n >= 15:
                alerts.append(("#EF4444", f"High readmission risk: {n} patients", datetime.now().strftime("%H:%M")))
            ns = s.get("likely_no_show_count", 0) or 0
            if ns >= 10:
                alerts.append(("#F59E0B", f"Likely no-shows tomorrow: {ns}", datetime.now().strftime("%H:%M")))
            if not alerts:
                alerts = [("#10B981", "No active alerts", datetime.now().strftime("%H:%M"))]
            items = [ui.tags.div(
                ui.tags.span(a[1], style="flex:1;"),
                ui.tags.span(a[2], style="color: var(--muted); font-size: 0.85rem;"),
                style=f"padding: 10px 12px; border-left: 4px solid {a[0]}; background: var(--surface2); border-radius: 6px; margin-bottom: 6px; display: flex; justify-content: space-between;",
            ) for a in alerts]
            return ui.tags.div(
                ui.tags.p("Active Alerts", style="font-size: 0.85rem; color: var(--muted); margin-bottom: 8px;"),
                ui.tags.div(*items, style="max-height: 180px; overflow-y: auto;"),
                style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px;",
            )
        except Exception as e:
            return _render_err("alerts_feed", e)

    # ─── AI Action Items (event-driven: only on Refresh AI Brief click) ─────
    ai_brief_text = reactive.Value("click_refresh")
    ai_loading = reactive.Value(False)

    @reactive.Effect
    @reactive.event(input.refresh_ai)
    def _refresh_ai_brief():
        ai_loading.set(True)
        try:
            ctx = r_strain()
            text = generate_operational_summary(ctx)
            ai_brief_text.set(text or "No summary available.")
        except Exception as e:
            _log_error("AI", "generate_operational_summary failed", e)
            ai_brief_text.set(f"AI unavailable: {e}")
        finally:
            ai_loading.set(False)

    @render.ui
    def cmd_action_items():
        try:
            text = ai_brief_text()
            loading = ai_loading()

            if loading:
                return ui.tags.div(
                    ui.tags.span("⏳ Generating AI analysis..."),
                    ui.tags.p("Action items", class_="card-title"),
                    style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); color: #64748B;",
                )

            if not text or str(text).strip() == "" or str(text).strip() == "click_refresh":
                return ui.tags.div(
                    ui.tags.p("Action items", class_="card-title"),
                    ui.tags.p(
                        "Click Refresh AI Brief to generate analysis.",
                        style="color: #64748B; padding: 16px; margin: 0;",
                    ),
                    style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border);",
                )

            # Parse text into bullets with icons (no AI call — text from event-driven refresh)
            bullets = [s.strip() for s in str(text).split(".") if len(s.strip()) > 20][:4]
            items = []
            for b in bullets:
                bl = b.lower()
                icon = (
                    "🚨"
                    if any(w in bl for w in ["escalat", "critical", "urgent", "immediate"])
                    else "⚠️"
                    if any(w in bl for w in ["monitor", "caution", "elevated", "watch"])
                    else "✅"
                    if any(w in bl for w in ["normal", "stable", "adequate", "no immediate"])
                    else "💡"
                )
                items.append(
                    ui.tags.li(
                        f"{icon} {b}.",
                        style="padding: 6px 0; border-bottom: 1px solid #F1F5F9;",
                    )
                )
            return ui.tags.div(
                ui.tags.p("Action items", class_="card-title"),
                ui.tags.ul(*items, style="list-style: none; padding: 0; margin: 0;"),
                style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border);",
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ui.tags.p(f"AI unavailable: {e}", style="color: #94A3B8; padding: 16px;")

    # ─── Discharge Pipeline ────────────────────────────────────────────────
    @render.ui
    def discharge_pipeline():
        try:
            ready_df, overdue_df, long_stay_df = r_discharge_pipeline()
            n_ready, n_overdue, n_long = len(ready_df), len(overdue_df), len(long_stay_df)
            pid_col = _safe_date_col(ready_df, ["patient_id", "patient"])
            adate_col = _safe_date_col(ready_df, ["admission_date", "admit_date", "start_date", "date"])
            def _table_df(d):
                if d.empty:
                    return pd.DataFrame()
                cols = [c for c in [pid_col, adate_col] if c and c in d.columns]
                return d[cols].head(200) if cols else d.head(200)

            cards = [
                ("Ready today", n_ready, "#10B981", "discharge_ready_btn", "Discharge pipeline — Ready today", _table_df(ready_df)),
                ("Overdue", n_overdue, "#EF4444", "discharge_overdue_btn", "Discharge pipeline — Overdue", _table_df(overdue_df)),
                ("Long stay (>7d)", n_long, "#F59E0B", "discharge_longstay_btn", "Discharge pipeline — Long stay", _table_df(long_stay_df)),
            ]
            row = []
            for label, count, color, btn_id, modal_title, tdf in cards:
                row.append(ui.tags.div(
                    ui.tags.div(label, style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 6px;"),
                    ui.input_action_button(btn_id, ui.tags.span(str(count), style=f"font-family: var(--mono); font-size: 1.75rem; font-weight: 600; color: {color}; cursor: pointer;"), style="border: none; background: transparent; padding: 0; cursor: pointer;"),
                    style=f"padding: 16px; background: var(--surface2); border-radius: 10px; border-left: 4px solid {color}; min-width: 120px;",
                ))
            return ui.tags.div(
                ui.tags.p("Discharge Pipeline", class_="card-title", style="margin-bottom: 12px;"),
                ui.tags.div(*row, style="display: flex; gap: 16px; flex-wrap: wrap;"),
                style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px;",
            )
        except Exception as e:
            return _render_err("discharge_pipeline", e)

    def _show_discharge_modal(title: str, df: pd.DataFrame, session):
        if df is None or df.empty:
            content = ui.tags.p("No patients in this group.", style="color: var(--muted);")
        else:
            content = ui.tags.div(ui.tags.p(f"{len(df)} patients", style="color: var(--muted); font-size: 0.85rem; margin-bottom: 8px;"), ui.HTML(_safe_html_table(df)))
        ui.modal_show(ui.modal(ui.modal_header(title), ui.modal_body(content), ui.modal_footer(ui.modal_button("Close")), size="lg", easy_close=True), session=session)

    @reactive.Effect
    @reactive.event(input.discharge_ready_btn)
    def _modal_discharge_ready():
        ready_df, overdue_df, long_stay_df = r_discharge_pipeline()
        pid_col = _safe_date_col(ready_df, ["patient_id", "patient"])
        adate_col = _safe_date_col(ready_df, ["admission_date", "admit_date", "start_date", "date"])
        tdf = ready_df[[c for c in [pid_col, adate_col] if c and c in ready_df.columns]].head(200) if not ready_df.empty and (pid_col or adate_col) else ready_df.head(200)
        _show_discharge_modal("Discharge pipeline — Ready today", tdf, session)

    @reactive.Effect
    @reactive.event(input.discharge_overdue_btn)
    def _modal_discharge_overdue():
        ready_df, overdue_df, long_stay_df = r_discharge_pipeline()
        pid_col = _safe_date_col(overdue_df, ["patient_id", "patient"])
        adate_col = _safe_date_col(overdue_df, ["admission_date", "admit_date", "start_date", "date"])
        tdf = overdue_df[[c for c in [pid_col, adate_col] if c and c in overdue_df.columns]].head(200) if not overdue_df.empty and (pid_col or adate_col) else overdue_df.head(200)
        _show_discharge_modal("Discharge pipeline — Overdue", tdf, session)

    @reactive.Effect
    @reactive.event(input.discharge_longstay_btn)
    def _modal_discharge_longstay():
        ready_df, overdue_df, long_stay_df = r_discharge_pipeline()
        pid_col = _safe_date_col(long_stay_df, ["patient_id", "patient"])
        adate_col = _safe_date_col(long_stay_df, ["admission_date", "admit_date", "start_date", "date"])
        tdf = long_stay_df[[c for c in [pid_col, adate_col] if c and c in long_stay_df.columns]].head(200) if not long_stay_df.empty and (pid_col or adate_col) else long_stay_df.head(200)
        _show_discharge_modal("Discharge pipeline — Long stay", tdf, session)

    # ─── Department Breakdown ─────────────────────────────────────────────
    @render.ui
    def department_breakdown():
        try:
            data = r_dept_breakdown()
            dept_rates = _df(data.get("dept_rates"))
            high_risk = _df(data.get("high_risk"))
            beds_df = _df(data.get("beds_df"))
            adm_df = _df(data.get("adm_df"))
            dept_col = next((c for c in dept_rates.columns if "department" in c.lower() or "dept" in c.lower()), None) if not dept_rates.empty else None
            rate_col = next((c for c in dept_rates.columns if "rate" in c.lower() or "no_show" in c.lower()), None) if not dept_rates.empty else None
            if dept_col is None and not dept_rates.empty:
                dept_col = dept_rates.columns[0]
            if rate_col is None and not dept_rates.empty:
                for c in dept_rates.columns:
                    if pd.api.types.is_numeric_dtype(dept_rates[c]):
                        rate_col = c
                        break
            unit_col = next((c for c in beds_df.columns if "unit" in c.lower() or "department" in c.lower() or "dept" in c.lower()), None) if not beds_df.empty else None
            adm_dept_col = next((c for c in adm_df.columns if "department" in c.lower() or "dept" in c.lower()), None) if not adm_df.empty else None
            readmit_by_dept = {}
            if not high_risk.empty and "patient_id" in high_risk.columns and not adm_df.empty and adm_dept_col and "patient_id" in adm_df.columns:
                try:
                    merge = high_risk[["patient_id"]].merge(adm_df[["patient_id", adm_dept_col]].drop_duplicates(), on="patient_id", how="left")
                    readmit_by_dept = merge.groupby(adm_dept_col).size().to_dict() if adm_dept_col in merge.columns else {}
                except Exception:
                    readmit_by_dept = {}
            rows = []
            if dept_rates.empty or dept_col is None:
                return ui.tags.div(ui.tags.p("Department Breakdown", class_="card-title"), ui.tags.p("No department data.", style="color: var(--muted);"), style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px;")
            for _, row in dept_rates.iterrows():
                dept_name = str(row.get(dept_col, "—"))
                no_show_rate = row.get(rate_col, "—")
                if pd.notna(no_show_rate) and isinstance(no_show_rate, (int, float)):
                    no_show_str = f"{float(no_show_rate)*100:.1f}%" if no_show_rate <= 1 else f"{no_show_rate:.1f}%"
                else:
                    no_show_str = str(no_show_rate) if no_show_rate != "—" else "—"
                icu_count = "—"
                if not beds_df.empty and unit_col and dept_name != "—":
                    icu_count = int((beds_df[unit_col].astype(str).str.lower() == dept_name.lower()).sum())
                readmit_count = readmit_by_dept.get(dept_name, readmit_by_dept.get(str(dept_name).strip(), "—"))
                if readmit_count == "—" and not readmit_by_dept:
                    readmit_count = "—"
                else:
                    readmit_count = str(readmit_count)
                status_color = "#10B981"
                if isinstance(no_show_rate, (int, float)) and (no_show_rate >= 0.25 or (no_show_rate >= 0.2 and no_show_rate <= 1)):
                    status_color = "#F59E0B"
                if isinstance(no_show_rate, (int, float)) and no_show_rate >= 0.3:
                    status_color = "#EF4444"
                rows.append(ui.tags.tr(
                    ui.tags.td(dept_name),
                    ui.tags.td(str(icu_count)),
                    ui.tags.td(readmit_count),
                    ui.tags.td(no_show_str),
                    ui.tags.td(ui.tags.span("●", style=f"color: {status_color}; font-size: 1.2rem;")),
                ))
            tbl = ui.tags.table(
                ui.tags.thead(ui.tags.tr(ui.tags.th("Department"), ui.tags.th("ICU"), ui.tags.th("Readmit risk"), ui.tags.th("No-show rate"), ui.tags.th(""))),
                ui.tags.tbody(*rows),
                style="width: 100%; font-size: 0.85rem; border-collapse: collapse;",
            )
            return ui.tags.div(
                ui.tags.p("Department Breakdown", class_="card-title", style="margin-bottom: 12px;"),
                tbl,
                style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px;",
            )
        except Exception as e:
            return _render_err("department_breakdown", e)

    # ─── ICU Capacity tab: trend + stats ──────────────────────────────────
    @render.plot
    def icu_trend_plot():
        _tick()  # time-series: refresh every minute
        try:
            df = r_trend()
            if df is None or df.empty:
                return _placeholder_plot("icu_trend_plot", "No trend data")
            fig, ax = plt.subplots(figsize=(10, 3.5))
            dates = pd.to_datetime(df["date"])
            ax.fill_between(dates, df["admissions"], alpha=0.15, color="#0F4C81")
            ax.plot(dates, df["admissions"], color="#0F4C81", linewidth=2, marker="o", markersize=4, label="Admissions")
            if "discharges" in df.columns:
                ax.plot(dates, df["discharges"], color="#0D9373", linewidth=2, marker="s", markersize=4, label="Discharges")
            ax.axhline(y=45, color="#DC2626", linestyle="--", alpha=0.6, linewidth=1, label="Critical (90%)")
            ax.axhline(y=35, color="#D97706", linestyle="--", alpha=0.6, linewidth=1, label="Caution (70%)")
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax.tick_params(axis="x", rotation=45)
            ax.set_ylabel("Count", color="#64748B")
            ax.legend(fontsize=8, framealpha=0.9)
            _style_ax(ax, fig)
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("icu_trend_plot", f"Chart error: {e}")

    @render.ui
    def icu_stats_cards():
        try:
            df = r_trend()
            if df is None or df.empty:
                avg_adm = peak = total_a = trend_dir = "—"
            else:
                avg_adm = f"{df['admissions'].mean():.1f}" if "admissions" in df.columns else "—"
                total_a = int(df["admissions"].sum()) if "admissions" in df.columns else "—"
                peak = int(df["admissions"].max()) if "admissions" in df.columns else "—"
                if len(df) >= 2 and "admissions" in df.columns:
                    trend_dir = "↑" if df["admissions"].iloc[-1] >= df["admissions"].iloc[0] else "↓"
                else:
                    trend_dir = "→"
            cards = [
                ("Avg Daily Admissions", avg_adm),
                ("Peak Occupancy (30d)", peak),
                ("Total Admissions (period)", total_a),
                ("Current Trend", trend_dir),
            ]
            return ui.tags.div(
                *[ui.tags.div(ui.tags.div(lbl, class_="card-title"), ui.tags.div(str(v), class_="metric-number", style="font-size: 1.5rem;"), style="padding: 16px; background: var(--surface2); border-radius: 8px; border: 1px solid var(--border); margin: 4px;") for lbl, v in cards],
                style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px;",
            )
        except Exception as e:
            return _render_err("icu_stats_cards", e)

    # ─── High Readmission tab ─────────────────────────────────────────────
    @render.ui
    def readmission_summary_bar():
        try:
            df, err = readmission_data()
            if err:
                return ui.tags.p("Error loading data.", style="color: var(--danger);")
            n = len(df) if df is not None else 0
            critical = len(df[df["readmission_risk"] >= 0.8]) if df is not None and not df.empty and "readmission_risk" in df.columns else 0
            high = len(df[(df["readmission_risk"] >= 0.6) & (df["readmission_risk"] < 0.8)]) if df is not None and not df.empty and "readmission_risk" in df.columns else 0
            mod = n - critical - high
            return ui.tags.div(
                ui.tags.p(f"{n} patients flagged for 30-day readmission risk ≥ 60%", style="margin-bottom: 12px;"),
                ui.tags.div(
                    ui.tags.span(f"🔴 Critical (≥80%): {critical}", style="margin-right: 16px;"),
                    ui.tags.span(f"🟡 High (60-80%): {high}", style="margin-right: 16px;"),
                    ui.tags.span(f"🟢 Moderate (<60%): {mod}"),
                ),
                style="padding: 16px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 16px;",
            )
        except Exception as e:
            return _render_err("readmission_summary_bar", e)

    @render.ui
    def readmission_cards():
        try:
            df, err = readmission_data()
            if err or df is None or df.empty:
                return ui.tags.p("No high-risk patients found.", style="color: var(--muted);")
            sort_by = input.risk_sort() if hasattr(input, "risk_sort") and input.risk_sort() else "risk"
            flt = input.risk_filter() if hasattr(input, "risk_filter") and input.risk_filter() else "all"
            if "readmission_risk" in df.columns:
                if flt == "critical":
                    df = df[df["readmission_risk"] >= 0.8]
                elif flt == "high":
                    df = df[(df["readmission_risk"] >= 0.6) & (df["readmission_risk"] < 0.8)]
                if sort_by == "risk" and "readmission_risk" in df.columns:
                    df = df.sort_values("readmission_risk", ascending=False)
                elif sort_by == "admissions" and "admission_count" in df.columns:
                    df = df.sort_values("admission_count", ascending=False)
                elif sort_by == "id" and "patient_id" in df.columns:
                    df = df.sort_values("patient_id")
            cards = []
            for _, row in df.head(50).iterrows():
                pid = row.get("patient_id", "—")
                risk = float(row.get("readmission_risk", 0)) if pd.notna(row.get("readmission_risk")) else 0
                adm = row.get("admission_count", "—")
                stripe = "#EF4444" if risk >= 0.8 else "#F59E0B"
                cards.append(
                    ui.tags.div(
                        ui.tags.div(style=f"height: 4px; background: {stripe}; border-radius: 12px 12px 0 0; margin: -20px -20px 12px -20px;"),
                        ui.tags.div(str(pid), style="font-family: var(--mono); font-size: 1.25rem; margin-bottom: 8px;"),
                        ui.tags.div(ui.tags.div(style=f"width: {risk*100}%; height: 8px; background: #EF4444; border-radius: 4px;"), style="width: 100%; height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; margin-bottom: 8px;"),
                        ui.tags.span(f"Risk: {risk*100:.1f}%", style="font-size: 0.85rem; color: var(--muted);"),
                        ui.tags.span(f"  Admissions: {adm}", style="font-size: 0.85rem; color: var(--muted);"),
                        style="width:100%; text-align:left; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px;",
                    )
                )
            return ui.tags.div(*cards, style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;")
        except Exception as e:
            return _render_err("readmission_cards", e)

    @reactive.effect
    def _readmission_view_dropdown():
        df, _ = readmission_data()
        if df is None or df.empty or "patient_id" not in df.columns:
            ui.update_select("readmission_view_patient", choices={}, session=session)
            return
        ids = df["patient_id"].astype(str).unique().tolist()[:100]
        choices = {pid: pid for pid in ids}
        ui.update_select("readmission_view_patient", choices=choices, selected=ids[0] if ids else None, session=session)

    @reactive.effect
    @reactive.event(input.readmission_view_btn)
    def _readmission_view_click():
        pid = input.readmission_view_patient()
        if not pid:
            return
        try:
            hist = safe_patient_history(str(pid))
            dem = hist.get("demographics")
            if dem is None:
                dem = {}
            risk_df = _df(hist.get("risk_scores"))
            adm_df = _df(hist.get("admissions"))
            parts = [pd.DataFrame([dem])] if dem else []
            if not risk_df.empty:
                parts.append(risk_df)
            if not adm_df.empty:
                parts.append(adm_df)
            combined = pd.concat(parts, axis=0, ignore_index=True) if parts else pd.DataFrame()
            if combined.empty:
                combined = pd.DataFrame([{"Patient ID": pid, "Info": "No history"}])
            show_patient_modal(f"Patient {pid} — Full History", combined, session)
        except Exception:
            pass

    @render.plot
    def readmission_dist_plot():
        try:
            df, _ = readmission_data()
            if df is None or df.empty or "readmission_risk" not in df.columns:
                return _placeholder_plot("readmission_dist_plot", "No data")
            fig, ax = plt.subplots(figsize=(7, 3))
            bins = [0.6, 0.7, 0.8, 0.9, 1.01]
            labels = ["0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]
            colors = ["#FEF08A", "#FCD34D", "#F97316", "#DC2626"]
            counts = []
            for i in range(len(bins) - 1):
                mask = (df["readmission_risk"] >= bins[i]) & (df["readmission_risk"] < bins[i + 1])
                counts.append(mask.sum())
            bars = ax.bar(labels, counts, color=colors, width=0.5)
            ax.set_xlabel("Risk Score Range", color="#64748B")
            ax.set_ylabel("Patient Count", color="#64748B")
            ax.set_title("Readmission Risk Distribution", color="#1E293B", fontsize=11)
            for bar, count in zip(bars, counts):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2, str(count), ha="center", fontsize=9, color="#1E293B")
            _style_ax(ax, fig)
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("readmission_dist_plot", f"Chart error: {e}")

    # ─── No-Show tab ──────────────────────────────────────────────────────
    @render.ui
    def noshow_summary_row():
        try:
            s = r_strain()
            n_ns = s.get("likely_no_show_count", 0) or 0
            df, _ = noshow_data()
            n_dept = len(df) if df is not None and not df.empty else 0
            return ui.tags.p(f"{n_ns} appointments at risk tomorrow across {n_dept} departments", style="margin-bottom: 16px; color: var(--muted);")
        except Exception as e:
            return _render_err("noshow_summary_row", e)

    @render.plot
    def noshow_bar_plot():
        try:
            df, _ = noshow_data()
            if df is None or df.empty:
                return _placeholder_plot("noshow_bar_plot", "No department data")
            fig, ax = plt.subplots(figsize=(7, 3.5))
            df = df.copy()
            if "no_show_rate" not in df.columns:
                rate_col = [c for c in df.columns if "rate" in c.lower()]
                rate_col = rate_col[0] if rate_col else df.columns[-1]
                df["no_show_rate"] = df[rate_col] if rate_col else 0
            df = df.sort_values("no_show_rate", ascending=True)
            rates = df["no_show_rate"] * 100
            depts = df["department"].str.capitalize() if "department" in df.columns else df.iloc[:, 0].astype(str)
            colors = ["#DC2626" if r > 20 else "#D97706" if r > 10 else "#0D9373" for r in rates]
            bars = ax.barh(depts, rates, color=colors, height=0.5)
            ax.axvline(x=20, color="#DC2626", linestyle="--", alpha=0.5, linewidth=1)
            ax.axvline(x=10, color="#D97706", linestyle="--", alpha=0.5, linewidth=1)
            ax.set_xlabel("No-Show Rate (%)", color="#64748B")
            for bar, rate in zip(bars, rates):
                ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2, f"{rate:.1f}%", va="center", fontsize=9, color="#1E293B")
            _style_ax(ax, fig)
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("noshow_bar_plot", f"Chart error: {e}")

    @render.ui
    def noshow_stats():
        try:
            df, _ = noshow_data()
            s = r_strain()
            n_at_risk = s.get("likely_no_show_count", 0) or 0
            if df is None or df.empty:
                high_dept = low_dept = overall = "—"
            else:
                rate_col = "no_show_rate" if "no_show_rate" in df.columns else [c for c in df.columns if "rate" in c.lower()]
                rate_col = rate_col[0] if isinstance(rate_col, list) and rate_col else (rate_col if isinstance(rate_col, str) else df.columns[-1])
                dept_col = "department" if "department" in df.columns else df.columns[0]
                high_dept = str(df.loc[df[rate_col].idxmax(), dept_col]) if len(df) else "—"
                low_dept = str(df.loc[df[rate_col].idxmin(), dept_col]) if len(df) else "—"
                overall = f"{df[rate_col].mean()*100:.1f}%" if rate_col in df.columns else "—"
            cards = [
                ("Highest Risk Dept", high_dept),
                ("Lowest Risk Dept", low_dept),
                ("Overall Rate", overall),
                ("Patients at Risk Tomorrow", str(n_at_risk)),
            ]
            return ui.tags.div(
                *[ui.tags.div(ui.tags.div(lbl, class_="card-title"), ui.tags.div(str(v), class_="metric-number", style="font-size: 1.25rem;"), style="padding: 16px; background: var(--surface2); border-radius: 8px; border: 1px solid var(--border); margin-bottom: 8px;") for lbl, v in cards],
                style="flex: 0 0 40%;",
            )
        except Exception as e:
            return _render_err("noshow_stats", e)

    @render.ui
    def noshow_patients_table_wrap():
        try:
            df = r_likely_no_shows()
            if df is None or df.empty:
                return ui.tags.p("No patients at risk.", style="color: var(--muted);")
            return ui.tags.div(
                ui.tags.p("Patients Likely to Miss Tomorrow's Appointment", style="margin-bottom: 8px;"),
                ui.output_data_frame("noshow_patients_table"),
                style="margin-top: 16px;",
            )
        except Exception as e:
            return _render_err("noshow_patients_table_wrap", e)

    @render.data_frame
    def noshow_patients_table():
        try:
            df = r_likely_no_shows()
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                _log("Render", "fallback noshow_patients_table: empty data")
                return render.DataGrid(pd.DataFrame([{"Message": "No data available"}]), height="400px")
            return render.DataGrid(df, height="400px")
        except Exception as e:
            import traceback
            traceback.print_exc()
            _log("Render", "noshow_patients_table error", error=str(e))
            return render.DataGrid(pd.DataFrame([{"Message": f"Error: {e}"}]), height="400px")

    # ─── Patient Twin tab ─────────────────────────────────────────────────
    @reactive.effect
    def _init_patient_select():
        ids = r_patient_ids()
        choices = {"": "Select..."}
        if ids:
            choices.update({i: i for i in ids})
            ui.update_select("patient_id", choices=choices, selected=ids[0] if ids else "", session=session)
        else:
            ui.update_select("patient_id", choices=choices, session=session)

    @render.ui
    @reactive.event(input.load_twin)
    def twin_mini_badge():
        try:
            hist = r_patient_history()
            if not hist:
                return ui.tags.div()
            try:
                rs = _df(hist.get("risk_scores"))
                if rs.empty or "readmission_risk" not in rs.columns:
                    risk = 0
                else:
                    risk = float(rs["readmission_risk"].max())
            except Exception:
                risk = 0
            color = "#EF4444" if risk >= 0.8 else ("#F59E0B" if risk >= 0.6 else "#10B981")
            return ui.tags.div(f"Risk: {risk*100:.0f}%", style=f"margin-top: 8px; padding: 6px 10px; background: {color}; border-radius: 20px; font-size: 0.85rem; text-align: center;")
        except Exception as e:
            return _render_err("twin_mini_badge", e)

    @render.ui
    @reactive.event(input.load_twin)
    def twin_demographics():
        try:
            hist = r_patient_history()
            if not hist:
                return ui.tags.p("Select a patient and click Load Twin.")
            dem = hist.get("demographics")
            if dem is None:
                dem = {}
            rs = _df(hist.get("risk_scores"))
            if not dem:
                return ui.tags.p("No demographics.", style="color: var(--muted);")
            risk_chips = []
            if not rs.empty:
                for col in rs.columns:
                    if col == "patient_id":
                        continue
                    v = rs[col].iloc[0] if len(rs) else None
                    if pd.notna(v):
                        try:
                            vf = float(v)
                            c = "#EF4444" if vf >= 0.8 else ("#F59E0B" if vf >= 0.6 else "#10B981")
                        except Exception:
                            c = "#6B8CAE"
                        risk_chips.append(ui.tags.span(f"{col}: {v}", style=f"padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; background: {c}; margin: 2px;"))
            return ui.tags.div(
                ui.tags.div(
                    ui.tags.div(ui.tags.table(ui.tags.tbody(*[ui.tags.tr(ui.tags.td(k, style="color: var(--muted);"), ui.tags.td(str(v))) for k, v in dem.items()])), style="flex:1;"),
                    ui.tags.div(*risk_chips, style="flex:1; display: flex; flex-wrap: wrap; align-items: flex-start;"),
                    style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;",
                ),
                style="padding: 20px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 16px;",
            )
        except Exception as e:
            return _render_err("twin_demographics", e)

    @render.plot
    @reactive.event(input.load_twin)
    def twin_vitals_plot():
        try:
            hist = r_patient_history()
            if not hist:
                fig, ax = plt.subplots(figsize=(8, 3))
                ax.text(0.5, 0.5, "Select a patient", ha="center", va="center", transform=ax.transAxes, color="#64748B")
                return fig
            pid = (input.patient_id() or "").strip()
            vitals = hist.get("vitals", pd.DataFrame())
            vitals = _df(vitals)
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4), sharex=True)
            if vitals.empty:
                ax1.text(0.5, 0.5, "No vitals data", ha="center", va="center", transform=ax1.transAxes, color="#64748B")
                _style_ax(ax1, fig)
                _style_ax(ax2, fig)
                return fig
            v = vitals.tail(20).copy()
            num_cols = v.select_dtypes(include="number").columns.tolist()
            c1 = "heart_rate" if "heart_rate" in v.columns else (num_cols[0] if num_cols else None)
            c2 = "oxygen_saturation" if "oxygen_saturation" in v.columns else (num_cols[1] if len(num_cols) > 1 else None)
            if c1 is not None:
                ax1.plot(range(len(v)), v[c1], color="#F97316", linewidth=2)
                if c1 == "heart_rate":
                    ax1.axhline(y=100, color="#DC2626", linestyle="--", alpha=0.5, linewidth=1)
                    ax1.axhline(y=60, color="#DC2626", linestyle="--", alpha=0.5, linewidth=1)
                ax1.set_ylabel(c1.replace("_", " ").title(), color="#64748B", fontsize=9)
            if c2 is not None:
                ax2.plot(range(len(v)), v[c2], color="#3B82F6", linewidth=2)
                if c2 == "oxygen_saturation":
                    ax2.axhline(y=95, color="#DC2626", linestyle="--", alpha=0.5, linewidth=1)
                ax2.set_ylabel(c2.replace("_", " ").title(), color="#64748B", fontsize=9)
            _style_ax(ax1, fig)
            _style_ax(ax2, fig)
            fig.suptitle(f"Vitals — Patient {pid}", color="#1E293B", fontsize=11)
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(0.5, 0.5, f"Error: {e}", ha="center", va="center", transform=ax.transAxes, color="#DC2626")
            return fig

    @render.plot
    @reactive.event(input.load_twin)
    def twin_admissions_plot():
        try:
            hist = r_patient_history()
            if not hist:
                fig, ax = plt.subplots(figsize=(8, 2))
                ax.text(0.5, 0.5, "Select a patient", ha="center", va="center", transform=ax.transAxes, color="#64748B")
                return fig
            pid = (input.patient_id() or "").strip()
            adm = _df(hist.get("admissions"))
            if adm.empty:
                fig, ax = plt.subplots(figsize=(8, 2))
                ax.text(0.5, 0.5, "No admissions", ha="center", va="center", transform=ax.transAxes, color="#64748B")
                _style_ax(ax, fig)
                return fig
            date_cols = [c for c in adm.columns if "date" in c.lower() or "admit" in c.lower() or "discharge" in c.lower()]
            if not date_cols:
                fig, ax = plt.subplots(figsize=(8, 2))
                ax.text(0.5, 0.5, "No date column", ha="center", va="center", transform=ax.transAxes, color="#64748B")
                return fig
            start_col = date_cols[0]
            adm = adm.copy()
            adm[start_col] = pd.to_datetime(adm[start_col], errors="coerce")
            adm = adm.dropna(subset=[start_col])
            if adm.empty:
                fig, ax = plt.subplots(figsize=(8, 2))
                ax.text(0.5, 0.5, "No valid dates", ha="center", va="center", transform=ax.transAxes, color="#64748B")
                return fig
            fig, ax = plt.subplots(figsize=(8, 2))
            ax.bar(range(len(adm)), [1] * len(adm), color="#3B82F6", width=0.6)
            ax.set_xticks(range(len(adm)))
            ax.set_xticklabels([str(d)[:10] for d in adm[start_col]], rotation=45, ha="right")
            ax.set_ylabel("Admissions", color="#64748B")
            ax.set_title(f"Admission events — Patient {pid}", color="#1E293B", fontsize=11)
            _style_ax(ax, fig)
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            fig, ax = plt.subplots(figsize=(8, 2))
            ax.text(0.5, 0.5, f"Error: {e}", ha="center", va="center", transform=ax.transAxes, color="#DC2626")
            return fig

    @render.ui
    @reactive.event(input.load_twin)
    def twin_risk_chips():
        try:
            hist = r_patient_history()
            if not hist:
                return ui.tags.div()
            rs = _df(hist.get("risk_scores"))
            if rs.empty:
                return ui.tags.p("No risk scores.", style="color: var(--muted);")
            chips = []
            for _, row in rs.iterrows():
                for c in rs.columns:
                    if c == "patient_id":
                        continue
                    v = row.get(c)
                    if pd.notna(v):
                        try:
                            vf = float(v)
                            color = "#EF4444" if vf >= 0.8 else ("#F59E0B" if vf >= 0.6 else "#10B981")
                        except Exception:
                            color = "#6B8CAE"
                        chips.append(ui.tags.span(f"{c}: {v}", style=f"display: inline-block; padding: 8px 14px; margin: 4px; border-radius: 8px; background: {color}; font-weight: 500;"))
            return ui.tags.div(*chips, style="margin-bottom: 16px;")
        except Exception as e:
            return _render_err("twin_risk_chips", e)

    @render.ui
    @reactive.event(input.load_twin)
    def twin_ai_explanation():
        try:
            hist = r_patient_history()
            pid = input.patient_id()
            if not pid or not hist:
                return ui.tags.div()
            text = explain_patient_risk(pid, hist)
            lines = [s.strip() for s in re.split(r"[.\n]+", str(text)) if len(s.strip()) > 10]
            bullets = lines[:8] if lines else [str(text)[:300]]
            return ui.tags.div(ui.tags.p("AI Explanation", class_="card-title"), ui.tags.ul(*[ui.tags.li(b, style="margin-bottom: 6px;") for b in bullets], style="padding-left: 20px; margin: 0;"))
        except Exception as e:
            return ui.tags.p(f"AI explanation unavailable: {e}", style="color: var(--muted);")


    # ─── Trends tab ────────────────────────────────────────────────────────
    @reactive.effect
    def _init_trend_dates():
        try:
            ui.update_date_range("trend_date_range", start=(datetime.now() - timedelta(days=30)).date(), end=datetime.now().date(), session=session)
        except Exception:
            pass

    @reactive.calc
    def trend_df():
        try:
            try:
                dr = input.trend_date_range()
                start = dr[0] if dr and len(dr) >= 1 else (datetime.now() - timedelta(days=30)).date()
                end = dr[1] if dr and len(dr) >= 2 else datetime.now().date()
            except Exception:
                start = (datetime.now() - timedelta(days=30)).date()
                end = datetime.now().date()
            df = r_trend_60()
            if df is None or df.empty or "date" not in df.columns:
                return pd.DataFrame()
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df[(df["date"] >= start) & (df["date"] <= end)]
            return df
        except Exception as e:
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    @render.plot
    def trend_main_plot():
        _tick()  # time-series: refresh every minute
        try:
            df = trend_df()
            if df is None or df.empty:
                return _placeholder_plot("trend_main_plot", "No trend data")
            fig, ax = plt.subplots(figsize=(10, 3.5))
            dates = pd.to_datetime(df["date"])
            ax.fill_between(dates, df["admissions"], alpha=0.15, color="#0F4C81")
            ax.plot(dates, df["admissions"], color="#0F4C81", linewidth=2, marker="o", markersize=4, label="Admissions")
            if "discharges" in df.columns:
                ax.fill_between(dates, df["discharges"], alpha=0.1, color="#0D9373")
                ax.plot(dates, df["discharges"], color="#0D9373", linewidth=2, marker="s", markersize=4, label="Discharges")
            if len(df) >= 7:
                ma = df["admissions"].rolling(7, min_periods=1).mean()
                ax.plot(dates, ma, color="#D97706", linewidth=1.5, linestyle="--", label="7-day avg")
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax.tick_params(axis="x", rotation=45)
            ax.set_ylabel("Count", color="#64748B")
            ax.legend(fontsize=8, framealpha=0.9)
            _style_ax(ax, fig)
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("trend_main_plot", f"Chart error: {e}")

    @render.plot
    def trend_net_plot():
        _tick()  # time-series: refresh every minute
        try:
            df = trend_df()
            if df is None or df.empty or "admissions" not in df.columns:
                return _placeholder_plot("trend_net_plot", "No trend data")
            fig, ax = plt.subplots(figsize=(10, 2.5))
            discharges = df["discharges"] if "discharges" in df.columns else pd.Series(0, index=df.index)
            net = df["admissions"] - discharges
            dates = pd.to_datetime(df["date"])
            colors = ["#0D9373" if n < 0 else "#DC2626" for n in net]
            ax.bar(dates, net, color=colors, width=0.7)
            ax.axhline(y=0, color="#64748B", linewidth=0.8)
            ax.set_ylabel("Net (Adm − Disch)", color="#64748B")
            ax.set_title("Net Daily Patient Flow", color="#1E293B", fontsize=11)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax.tick_params(axis="x", rotation=45)
            _style_ax(ax, fig)
            return fig
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _placeholder_plot("trend_net_plot", f"Chart error: {e}")

    @render.ui
    def trend_stats():
        try:
            df = trend_df()
            if df is None or df.empty:
                avg = peak = total = direction = "—"
            else:
                avg = f"{df['admissions'].mean():.1f}" if "admissions" in df.columns else "—"
                total = int(df["admissions"].sum()) if "admissions" in df.columns else "—"
                peak = str(df["date"].iloc[df["admissions"].argmax()]) if "admissions" in df.columns and len(df) else "—"
                direction = "↑" if len(df) >= 2 and df["admissions"].iloc[-1] > df["admissions"].iloc[0] else ("↓" if len(df) >= 2 else "→")
            return ui.tags.div(
                *[ui.tags.div(ui.tags.div(lbl, class_="card-title"), ui.tags.div(str(v), class_="metric-number", style="font-size: 1.25rem;"), style="padding: 16px; background: var(--surface2); border-radius: 8px; border: 1px solid var(--border);") for lbl, v in [("Avg Daily Admissions", avg), ("Peak Day", peak), ("Total Admissions (period)", total), ("Trend Direction", direction)]],
                style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px;",
            )
        except Exception as e:
            return _render_err("trend_stats", e)

    # ─── AI Assistant ────────────────────────────────────────────────────
    ai_history = reactive.Value([])

    @reactive.effect
    @reactive.event(input.btn_q1)
    def _q1():
        ui.update_text_area("user_question", value="Who needs attention today?", session=session)

    @reactive.effect
    @reactive.event(input.btn_q2)
    def _q2():
        ui.update_text_area("user_question", value="What is the ICU risk forecast for tomorrow?", session=session)

    @reactive.effect
    @reactive.event(input.btn_q3)
    def _q3():
        ui.update_text_area("user_question", value="Which department has the most no-shows this week?", session=session)

    @reactive.effect
    @reactive.event(input.btn_q4)
    def _q4():
        ui.update_text_area("user_question", value="Summarize readmission risk trends", session=session)

    @reactive.effect
    @reactive.event(input.clear_chat)
    def _clear():
        ai_history.set([])
        ui.update_text_area("user_question", value="", session=session)

    @render.ui
    @reactive.event(input.ask_ai)
    def ai_answer():
        try:
            q = (input.user_question() or "").strip()
            if not q:
                return ui.tags.p("Enter a question and click Ask AI.")
            data_context = r_strain()
            answer = answer_user_question(q, data_context)
            lines = [s.strip() for s in re.split(r"\n", str(answer)) if s.strip()]
            if len(lines) > 1:
                content = ui.tags.ul(*[ui.tags.li(l, style="margin-bottom: 4px;") for l in lines], style="padding-left: 20px; margin: 0;")
            else:
                content = ui.tags.p(str(answer))
            hist = list(ai_history()) + [(q, str(answer))]
            ai_history.set(hist[-3:])
            return ui.tags.div(
                ui.tags.div(q, style="text-align: right; background: var(--primary); color: #fff; padding: 12px; border-radius: 12px; margin: 8px 0; max-width: 80%; margin-left: auto;"),
                ui.tags.div(content, style="text-align: left; background: var(--surface2); padding: 12px; border-radius: 12px; margin: 8px 0;"),
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ui.tags.div(
                ui.tags.div((input.user_question() or "").strip() or "Q", style="text-align: right; background: var(--primary); color: #fff; padding: 12px; border-radius: 12px; margin: 8px 0; max-width: 80%; margin-left: auto;"),
                ui.tags.div(f"AI unavailable: {e}", style="text-align: left; background: var(--surface2); padding: 12px; border-radius: 12px; margin: 8px 0; color: var(--danger);"),
            )

    # ─── Footer ───────────────────────────────────────────────────────────
    @render.ui
    def footer_bar():
        try:
            env_ok = "Supabase ✓" if os.environ.get("SUPABASE_URL") and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")) else "Supabase ✗"
            s = r_strain()
            if s.get("data_as_of"):
                return ui.tags.span(f"⚠️ Demo data — as of {s['data_as_of']} | Auto-refresh: 60s | {env_ok}")
            return ui.tags.span(f"Last refreshed: {last_refresh()} | Auto-refresh: 60s | {env_ok}")
        except Exception as e:
            return _render_err("footer_bar", e)


app = App(app_ui, server)

if __name__ == "__main__":
    from shiny import run_app
    run_app(app, launch_browser=True)
