# Hospital Operations Command Center — Documentation

Easy-to-follow reference for every module and function: what it does, inputs, parameters, and return values.

---

## Table of contents

1. [Overview & architecture](#1-overview--architecture)
2. [Running the app & environment](#2-running-the-app--environment)
3. [Module: constants](#3-module-constants)
4. [Module: dashboard_log](#4-module-dashboard_log)
5. [Module: database_connection](#5-module-database_connection)
6. [Module: hospital_analytics](#6-module-hospital_analytics)
7. [Module: data_queries](#7-module-data_queries)
8. [Module: analytics](#8-module-analytics)
9. [Module: forecasting](#9-module-forecasting)
10. [Module: hospital_ai_agent](#10-module-hospital_ai_agent)
11. [Module: llm_insights](#11-module-llm_insights)
12. [Module: streamlit_dashboard](#12-module-streamlit_dashboard)

---

## 1. Overview & architecture

The app is a **Streamlit dashboard** that reads hospital data from **Supabase** (PostgreSQL via REST), computes analytics and trends, and optionally uses an **LLM** (OpenAI-compatible API) for recommendations and natural-language answers.

**Data flow (simplified):**

```
Supabase (patients, admissions, icu_beds, risk_scores, appointments, vitals)
    ↓
database_connection.py  (fetch tables)
    ↓
hospital_analytics.py    (strain, readmission, no-show, trends, patient history)
data_queries.py         (trend series for charts)
    ↓
analytics.py            (root-cause analysis, strain score formula)
forecasting.py          (ICU projections)
hospital_ai_agent.py    (LLM: recommendations, situation brief, Q&A)
    ↓
streamlit_dashboard.py  (UI: tabs, charts, filters, drill-downs)
```

**File roles:**

| File | Role |
|------|------|
| `streamlit_dashboard.py` | Main app entry; tabs, KPIs, charts, drill-down pages |
| `hospital_analytics.py` | Core metrics: system strain, high-risk patients, no-shows, admissions trend, patient history |
| `database_connection.py` | Supabase REST client; fetch tables as DataFrames |
| `data_queries.py` | Time-series data for ICU / readmission / no-show trend charts |
| `analytics.py` | Readmission drivers (conditions, departments, discharge types), hospital strain score formula |
| `forecasting.py` | Simple ICU occupancy projections (12h, 24h, 48h) |
| `hospital_ai_agent.py` | LLM calls: recommendations, situation brief, patient insight, Q&A |
| `llm_insights.py` | Re-exports LLM helpers for the dashboard |
| `constants.py` | Column names and empty-DataFrame contracts |
| `dashboard_log.py` | Optional debug logging (DEBUG=1) |

---

## 2. Running the app & environment

**Run:**

```bash
cd hospital_dashboard
pip install -r requirements.txt
streamlit run streamlit_dashboard.py
```

**Environment variables** (e.g. in `.env` in `hospital_dashboard/` or in the shell):

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL (e.g. `https://xxxx.supabase.co`) |
| `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_KEY` | Yes | Supabase API key |
| `OPENAI_API_KEY` or `LLM_API_KEY` | No | For AI tab, situation brief, recommendations, patient insight |
| `OPENAI_BASE_URL` | No | Override API base URL (default: OpenAI) |
| `LLM_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `DEBUG` | No | Set to `1`, `true`, or `yes` to enable pipeline logging |

---

## 3. Module: constants

**File:** `constants.py`  
**Purpose:** Single place for column names and empty-DataFrame shapes so all layers stay in sync.

### Constants (strings)

| Name | Value | Use |
|------|--------|-----|
| `PATIENT_ID_COL` | `"patient_id"` | Patient identifier column |
| `READMISSION_RISK_COL` | `"readmission_risk"` | Risk score column (0.0–1.0) |
| `APPOINTMENT_DATE_COL` | `"appointment_date"` | Appointment date column |
| `DEPARTMENT_COL` | `"department"` | Department name |
| `NO_SHOW_COL` | `"no_show"` | No-show flag |
| `ADMISSION_DATE_COL` | `"admission_date"` | Admission date |
| `DISCHARGE_DATE_COL` | `"discharge_date"` | Discharge date |
| `NO_SHOW_RATE_COL` | `"no_show_rate"` | No-show rate |
| `EXPECTED_DISCHARGE_DATE_COL` | `"expected_discharge_date"` | Expected discharge |

### Empty DataFrame column lists

| Name | Columns |
|------|---------|
| `HIGH_RISK_EMPTY_COLS` | `[patient_id, readmission_risk, admission_count]` |
| `DEPT_NO_SHOW_EMPTY_COLS` | `[department, total_appointments, no_shows, no_show_rate]` |
| `TREND_EMPTY_COLS` | `[date, admissions, discharges]` |

---

## 4. Module: dashboard_log

**File:** `dashboard_log.py`  
**Purpose:** Optional structured logging; errors always logged when passed to `log_error`.

### Functions

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `log(stage, message, **kwargs)` | `stage`: label (e.g. `"Analytics"`), `message`: string, `**kwargs`: key=value | `None` | Prints only when `DEBUG=1` (or `true`/`yes`). |
| `log_error(stage, message, error=None)` | `stage`, `message`, optional `error` exception | `None` | Always prints; use for failures. |
| `log_empty(stage, query_or_step, row_count=0)` | `stage`, `query_or_step` name, `row_count` | `None` | Logs when a step returns no rows; full line only if DEBUG. |

**Module-level:** `DEBUG` is `True` when env `DEBUG` is `1`, `true`, or `yes`.

---

## 5. Module: database_connection

**File:** `database_connection.py`  
**Purpose:** Fetch Supabase tables as pandas DataFrames via REST. No business logic. Loads `.env` from current dir, `hospital_dashboard/`, or project root.

### Public functions

#### `test_connection() -> bool`

- **Returns:** `True` if Supabase is reachable and credentials work.
- **Use:** Sanity check before running the app.

---

#### `normalize_dates(df, date_columns=None) -> pd.DataFrame`

- **Parameters:**
  - `df`: DataFrame to modify (copy is used).
  - `date_columns`: Optional list of column names. If `None`, infers columns whose name contains `date`, `time`, `_at`, `timestamp`, or `recorded`.
- **Returns:** DataFrame with those columns converted to `pd.Timestamp` (errors coerced).
- **Use:** Standardize date columns after fetch.

---

#### `get_patients() -> pd.DataFrame`

- **Returns:** Full `patients` table (capped by internal max rows). Uses shared in-memory cache (TTL 60s).
- **Typical columns:** `patient_id`, demographics, etc.

---

#### `get_admissions() -> pd.DataFrame`

- **Returns:** `admissions` table (capped). Cached.
- **Typical columns:** `admission_id`, `patient_id`, `admission_date`, `discharge_date`, etc.

---

#### `get_vitals() -> pd.DataFrame`

- **Returns:** `vitals` table (capped). Cached.

---

#### `get_vitals_for_patient(patient_id: str) -> pd.DataFrame`

- **Parameters:** `patient_id`: single patient ID.
- **Returns:** Vitals rows for that patient only (no cache; avoids loading full vitals table).
- **Use:** Patient Twin / single-patient views.

---

#### `get_appointments() -> pd.DataFrame`

- **Returns:** `appointments` table (capped). Cached.

---

#### `get_icu_beds() -> pd.DataFrame`

- **Returns:** `icu_beds` table (capped at 500 rows). Cached.
- **Typical columns:** `bed_id`, `occupied` or `status`, optionally `patient_id`.

---

#### `get_risk_scores() -> pd.DataFrame`

- **Returns:** `risk_scores` table (capped). Cached.
- **Typical columns:** `patient_id`, `readmission_risk`, `no_show_risk`, `icu_risk` (values 0.0–1.0 or 0–100 normalized elsewhere).

---

## 6. Module: hospital_analytics

**File:** `hospital_analytics.py`  
**Purpose:** Compute all Command Center metrics: strain, ICU, readmission, no-show, trends, patient history. Uses `database_connection` and `constants`.

### Public functions

#### `get_data_reference_date() -> pd.Timestamp`

- **Returns:** “Today” for the app: latest date in `admissions` or `appointments`. Falls back to `pd.Timestamp.now()` if no dates.
- **Use:** So the dashboard works with historical datasets (e.g. fixed date range) instead of real “now”.

---

#### `get_total_patients() -> int`

- **Returns:** Number of distinct patients (from `patients` table, e.g. `patient_id.nunique()`).
- **Use:** KPI “Total patients”.

---

#### `get_icu_occupancy() -> dict`

- **Returns:**  
  `total`, `occupied`, `rate` (0–1), `high_operational_risk` (True if rate ≥ 90%).
- **Logic:** Infers occupancy from `icu_beds` (`occupied` or `status`, or non-null `patient_id`).
- **Use:** ICU gauge and bed grid.

---

#### `compute_icu_occupancy() -> dict`

- **Returns:** Same as `get_icu_occupancy()`.
- **Use:** Alias for the same metric.

---

#### `get_system_strain() -> dict`

- **Returns:** One dict with all Command Center metrics, e.g.:
  - `icu_rate`, `readmit_rate`, `noshow_rate` (0–1)
  - `strain_score` (0–100), `strain_level` (`"normal"` / `"elevated"` / `"critical"`)
  - `discharge_pending`, `admissions_today`, `discharges_today`
  - `total_patients`, `icu_total`, `icu_occupied`
  - `high_readmission_count`, `likely_no_show_count`
  - `admissions_trend_records`, `department_no_show_records`
  - `data_as_of` (formatted date string)
- **Use:** Single source of truth for KPIs and LLM context; call once per page load.

---

#### `get_high_risk_patients(limit=20) -> pd.DataFrame`

- **Parameters:** `limit`: max number of rows.
- **Returns:** Patients with readmission risk ≥ 0.6, sorted by risk, with display-friendly columns when possible.
- **Use:** Alias for `get_high_readmission_patients(limit)`.

---

#### `get_high_readmission_patients(limit=20) -> pd.DataFrame`

- **Parameters:** `limit`: max rows (e.g. 100 or 500 for dashboard).
- **Returns:** DataFrame of high readmission-risk patients (risk ≥ 0.6). Uses `risk_scores` (and optionally `patients`, `admissions`). Columns typically include `patient_id`, `readmission_risk`, and optionally merged demographics.
- **Use:** Readmission Risk tab and root-cause analysis.

---

#### `get_likely_no_shows(days_ahead=1) -> pd.DataFrame`

- **Parameters:** `days_ahead`: how many days ahead to look for appointments.
- **Returns:** Appointments in that window that are likely no-shows (from risk_scores or heuristic). Fallbacks: upcoming appointments, then historical no-shows in last 30 days.
- **Use:** “Likely no-shows” count and list.

---

#### `get_admissions_trend(days=30) -> pd.DataFrame`

- **Parameters:** `days`: number of days back from reference date.
- **Returns:** DataFrame with columns `date`, `admissions`, `discharges` (daily counts). Expands the window if there are too few distinct dates.
- **Use:** Admissions/discharges and net-flow charts.

---

#### `get_no_show_rates() -> pd.DataFrame`

- **Returns:** Same as `get_department_no_show_rates()`.
- **Use:** No-show rate by department.

---

#### `get_department_no_show_rates() -> pd.DataFrame`

- **Returns:** DataFrame with columns like `department`, `total_appointments`, `no_shows`, `no_show_rate`. Aggregated from `appointments` (no_show or status column).
- **Use:** No-Show Risk tab (department bar chart).

---

#### `get_patient_id_list(max_ids=500) -> list[str]`

- **Parameters:** `max_ids`: cap on number of IDs returned.
- **Returns:** Sorted list of patient IDs for dropdowns.
- **Use:** Patient Twin tab and drill-down selectors.

---

#### `get_patient_history(patient_id: str | int) -> dict`

- **Parameters:** `patient_id`: one patient ID.
- **Returns:** Dict with:
  - `demographics`: dict from `patients` row
  - `risk_scores`: DataFrame (risk_scores for that patient)
  - `vitals`: DataFrame (from `get_vitals_for_patient`)
  - `admissions`: DataFrame (admissions for that patient)
- **Use:** Patient Digital Twin view and LLM patient insight.

---

## 7. Module: data_queries

**File:** `data_queries.py`  
**Purpose:** Build time-series DataFrames for trend charts. Uses `database_connection` and `get_data_reference_date()` from `hospital_analytics`.

### Functions

#### `get_trend_data(metric_name, *, hours_24=False, days_7=True) -> pd.DataFrame`

- **Parameters:**
  - `metric_name`: one of `"icu_occupancy"`, `"readmission_risk"`, `"no_show"`.
  - `hours_24`: reserved (not used for daily series).
  - `days_7`: if True, last 7 days; else last 30 days.
- **Returns:** DataFrame with columns `date` and `value`:
  - **icu_occupancy:** daily proxy % (0–100) from admissions/discharges (no historical ICU snapshot).
  - **readmission_risk:** daily count of high-risk patients (e.g. discharged that day with readmission_risk ≥ 0.6).
  - **no_show:** daily count of no-show appointments.
- **Use:** Trends tab line charts; optional input for forecasting.

---

## 8. Module: analytics

**File:** `analytics.py`  
**Purpose:** Root-cause analysis for readmission and operational strain score (separate from `hospital_analytics` strain).

### Functions

#### `analyze_readmission_drivers(df: pd.DataFrame) -> dict`

- **Parameters:** `df`: high-risk patients DataFrame (e.g. from `get_high_readmission_patients`), with optional columns for diagnosis, department, discharge type.
- **Returns:**  
  `top_conditions`, `departments`, `discharge_types` — each a list of `{"name": str, "count": int}`. Column names are inferred (e.g. contains `diagnos`, `department`, `discharge_type`).
- **Use:** “Top drivers of readmission risk” section and bar charts.

---

#### `hospital_strain_score(icu_occupancy_pct, readmission_rate, no_show_rate) -> tuple[float, str]`

- **Parameters:** All in 0–1 scale (e.g. 90% ICU → 0.9). If `icu_occupancy_pct` > 1, it is treated as 0–100 and normalized to 0–1.
- **Returns:** `(score, status)`:
  - `score`: 0–100 (formula: `0.5*ICU + 0.3*readmission + 0.2*no_show`).
  - `status`: `"normal"` (0–30), `"elevated"` (30–60), `"critical"` (60+).
- **Use:** Banner “Hospital Strain Score” and status color (green / yellow / red).

---

## 9. Module: forecasting

**File:** `forecasting.py`  
**Purpose:** Simple ICU occupancy projections (no external ML).

### Functions

#### `predict_icu_load(current_rate, historical_data=None, icu_total_beds=50) -> dict`

- **Parameters:**
  - `current_rate`: current ICU occupancy, 0–100 or 0–1 (normalized to 0–100).
  - `historical_data`: optional DataFrame with `date` and `value` (e.g. from `get_trend_data("icu_occupancy")`).
  - `icu_total_beds`: reserved for future use.
- **Returns:** `{"next_12h": float, "next_24h": float, "next_48h": float}` — projected occupancy % (0–100). Uses linear trend from last 5 points of `historical_data` if present; otherwise small deterministic drift.
- **Use:** “Projected ICU occupancy” metrics (12h / 24h / 48h).

---

## 10. Module: hospital_ai_agent

**File:** `hospital_ai_agent.py`  
**Purpose:** All LLM calls: summaries, recommendations, situation brief, patient insight, and Q&A. Uses OpenAI-compatible API; requires `OPENAI_API_KEY` or `LLM_API_KEY` for AI features.

### Public functions

#### `generate_operational_summary(data_context: dict) -> str`

- **Parameters:** `data_context`: dict from `get_system_strain()` (strain, counts, trend records, department no-show).
- **Returns:** Short operational summary (2–4 sentences) using only that data.
- **Use:** Optional summary block; dashboard mainly uses situation brief and recommendations.

---

#### `explain_patient_risk(patient_id, history: dict) -> str`

- **Parameters:** `patient_id`: string or int; `history`: dict from `get_patient_history(patient_id)`.
- **Returns:** Plain-text explanation of the patient’s risk profile (readmission, vitals if present). No invented numbers.
- **Use:** Patient Twin “AI Risk Explanation”.

---

#### `predict_capacity_alerts(data_context: dict) -> str`

- **Parameters:** Same `data_context` as above (ICU + trend).
- **Returns:** Text summary of ICU capacity and optional actions.
- **Use:** Capacity-focused alerts if needed.

---

#### `answer_user_question(question: str, data_context: dict) -> str`

- **Parameters:** `question`: user’s natural-language question; `data_context`: from `get_system_strain()`.
- **Returns:** Answer based only on `data_context` (no invented data).
- **Use:** AI Assistant tab.

---

#### `generate_operational_recommendations(summary_data: dict) -> str`

- **Parameters:** `summary_data`: dict with at least `icu_rate` (or icu occupancy), `icu_occupied`, `icu_total`, `high_readmission_count`, `likely_no_show_count` (or `likely_noshows`).
- **Returns:** Three actionable recommendations (action, reason, impact) as text.
- **Use:** Command Center “Operational Recommendations” block.

---

#### `generate_situation_brief(summary_data: dict) -> str`

- **Parameters:** `summary_data`: full strain dict (e.g. `get_system_strain()`).
- **Returns:** One short executive paragraph (ICU, readmission, no-show, priorities).
- **Use:** “AI Hospital Situation Brief” at top of Command Center.

---

#### `patient_digital_twin_insight(patient_id, history: dict) -> str`

- **Parameters:** Same as `explain_patient_risk`.
- **Returns:** Text covering readmission probability, risk factors, and suggested follow-up.
- **Use:** Patient Twin “Patient Digital Twin Insight” block.

---

## 11. Module: llm_insights

**File:** `llm_insights.py`  
**Purpose:** Single import surface for dashboard LLM features; no logic, only re-exports.

### Exports

- `generate_operational_recommendations`
- `generate_situation_brief`
- `patient_digital_twin_insight`

All are implemented in `hospital_ai_agent`; see [Module: hospital_ai_agent](#10-module-hospital_ai_agent).

---

## 12. Module: streamlit_dashboard

**File:** `streamlit_dashboard.py`  
**Purpose:** Streamlit UI: page config, sidebar, tabs, drill-down pages, and all charts/metrics.

### Entry point

- **`main()`:** Sets page config, session state, loads strain, injects CSS, renders navbar, strain score banner, sidebar (filters, navigation), and either drill-down view or tabbed dashboard. Call from `if __name__ == "__main__": main()`.
- **Run:** `streamlit run streamlit_dashboard.py` (from `hospital_dashboard/` or with correct path).

### Cached data loaders (all `@st.cache_data(ttl=60)`)

| Function | Parameters | Returns | Use |
|----------|------------|---------|-----|
| `load_strain()` | — | `get_system_strain()` | Navbar + KPIs + LLM context |
| `load_readmission(limit=100)` | `limit` | `get_high_readmission_patients(limit)` | Readmission Risk tab |
| `load_trend(days=30)` | `days` | `get_admissions_trend(days)` | Admissions/discharges charts |
| `load_noshow_dept()` | — | `get_department_no_show_rates()` | No-Show tab |
| `load_noshow_patients()` | — | `get_likely_no_shows()` | No-show count and list |
| `load_patient_ids()` | — | `get_patient_id_list()` | Patient Twin dropdown |
| `load_trend_data(metric_name, days_7=True)` | `metric_name`, `days_7` | `get_trend_data(...)` or empty DataFrame on error | Trends tab line charts |
| `load_patients_table()` | — | Merged DataFrame: patients + risk_scores + icu_status | Drill-down patient lists and filters |

### Helper functions (internal)

| Function | Purpose |
|----------|---------|
| `_records_to_df(records)` | Convert list of dicts to DataFrame; empty DataFrame if invalid. |
| `_plotly_layout()` | Returns shared Plotly layout dict (white/light theme, grid, margins). |
| `_render_drilldown_page(strain, diagnosis_filter)` | Renders patient list or Patient Twin based on `st.session_state.page` and filters. |
| `_render_patient_twin(strain, patient_id)` | Renders single Patient Digital Twin: demographics, vitals, risk, AI explanation, twin insight, admissions. |

### Tabs (in order)

1. **Command Center** — Strain banner, situation brief, KPIs + drill-down buttons, ICU gauge, bed grid, alerts, recommendations, ICU forecast.
2. **ICU Capacity** — Gauge, bed grid, 30-day admissions/discharges chart.
3. **Readmission Risk** — Counts, filters/sort, risk cards (batched HTML), root-cause drivers, risk distribution chart.
4. **No-Show Risk** — Department no-show chart, stats, at-risk appointments table.
5. **Patient Twin** — Patient selector, Load Patient Twin, vitals chart, risk scores, AI explanation, digital twin insight.
6. **Trends** — ICU / readmission / no-show line charts (7 or 30 days), then admissions & discharges (60-day) and net flow.
7. **AI Assistant** — Preset question buttons, text input, Q&A history.

### Session state (main keys)

- `page`: `"dashboard"` | `"patients"` | `"icu_patients"` | `"readmission_risk"` | `"no_shows"` | `"patient_twin"`.
- `patient_twin_id`: selected patient for Twin view.
- `sidebar_age_min`, `sidebar_age_max`, `sidebar_icu_only`, `sidebar_high_risk_only`, `sidebar_risk_min`, `sidebar_risk_max`, `sidebar_readmit_dept`: filters for patient lists and readmission tab.
- `ai_question`, `ai_history`: AI Assistant input and last N answers.

---

## Quick reference: “Where is X?”

| Need | Module / function |
|------|-------------------|
| Fetch any Supabase table | `database_connection.get_*` |
| “Today” for the app | `hospital_analytics.get_data_reference_date()` |
| All KPIs in one call | `hospital_analytics.get_system_strain()` |
| High readmission list | `hospital_analytics.get_high_readmission_patients(limit)` |
| No-show by department | `hospital_analytics.get_department_no_show_rates()` |
| Admissions/discharges trend | `hospital_analytics.get_admissions_trend(days)` |
| ICU / readmission / no-show trend series | `data_queries.get_trend_data(metric_name, days_7=...)` |
| Readmission drivers (conditions, depts, discharge) | `analytics.analyze_readmission_drivers(df)` |
| Strain score 0–100 + status | `analytics.hospital_strain_score(icu, readmit, noshow)` |
| ICU 12h/24h/48h projection | `forecasting.predict_icu_load(rate, historical_df)` |
| LLM recommendations | `hospital_ai_agent.generate_operational_recommendations(strain)` |
| LLM situation brief | `hospital_ai_agent.generate_situation_brief(strain)` |
| LLM patient insight | `hospital_ai_agent.patient_digital_twin_insight(pid, history)` |
| LLM Q&A | `hospital_ai_agent.answer_user_question(question, strain)` |
| Patient history for Twin | `hospital_analytics.get_patient_history(patient_id)` |

---

*End of documentation.*
