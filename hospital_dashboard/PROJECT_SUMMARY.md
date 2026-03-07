# Patient Digital Twin Hospital Dashboard — Project Summary

Use this summary when continuing in a new chat or onboarding.

---

## Project overview

- **App:** Python Shiny dashboard — **Hospital Operations Command Center**
- **Location:** `hospital_dashboard/` (run from here or project root)
- **Stack:** Shiny for Python, pandas, Supabase (REST API, no `supabase` package), OpenAI-compatible LLM, matplotlib
- **Data:** Supabase tables — `patients`, `admissions`, `vitals`, `appointments`, `icu_beds`, `risk_scores`

---

## Environment and run

- **Virtual env:** `.venv` in `hospital_dashboard/`
- **Run:** `./run.sh` (or `run.bat` on Windows) — uses `.venv` automatically
- **Alternative:** `source .venv/bin/activate` then `shiny run app.py`
- **.env** (in `hospital_dashboard/`, do not commit):
  - **Required:** `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_KEY`)
  - **Optional:** `OPENAI_API_KEY` (or `LLM_API_KEY`), `OPENAI_BASE_URL`, `LLM_MODEL`
- **Debug mode:** `DEBUG=1 ./run.sh` — logs full pipeline (Supabase, analytics, Shiny) to terminal; errors always logged

---

## UI theme and styling

- **Theme CSS:** `www/theme.css` — clinical palette (primary `#0F4C81`, success/warning/danger), cards, navbar, tables, buttons
- **Theme constants in app:** `THEME` dict in `app.py` for inline styles and charts
- **ICU severity colors:** `ICU_SEVERITY` — green &lt;70%, yellow 70–90%, red ≥90%

---

## Dashboard structure (nav panels)

1. **Command Center** (default)  
   - Critical Alerts (ICU + AI capacity alerts)  
   - Hospital Status (4 KPI value boxes: total patients, ICU occupancy, high readmission count, likely no-shows)  
   - **ICU Capacity Status** — visual component (see below)  
   - AI Operational Brief (LLM summary)  

2. **ICU Capacity**  
   - Alert banner when ≥90%  
   - ICU capacity dashboard (same visual component)  
   - ICU Occupancy Trend plot  

3. **High Readmission Risk** — table (reactive calc + message UI for errors/empty)  
4. **No-Show Risk** — department no-show table (reactive calc + message UI)  
5. **Patient Twin** — sidebar patient selector, demographics, vitals, admissions, risk scores, AI explanation  
6. **Trends** — admissions/discharges plot, ICU utilization plot  
7. **AI Assistant** — Q&A with LLM over hospital data  

---

## ICU capacity dashboard (visual component)

- **Output:** `icu_capacity_dashboard` (`@render.ui`)
- **Data:** `safe_icu_occupancy()` → total, occupied, rate, high_operational_risk
- **Content:**  
  - **Metrics row:** Total beds | Occupied | Occupancy % (color by severity) | Remaining  
  - **Capacity bar:** Filled (severity color) vs empty (gray), proportion = occupancy  
  - **Operational guidance bullets:** Monitor admission trend; prepare surge staffing if approaching 90%; review discharge pipeline  
- **Severity:** Green &lt;70%, Yellow 70–90%, Red ≥90% (border, occupancy color, bar fill)
- Used in Command Center and ICU Capacity panel

---

## Layered architecture

1. **Data repository** (`database_connection.py`)  
   - Handles all Supabase queries only. No business logic.  
   - `_fetch_table()`, `get_patients()`, `get_admissions()`, `get_icu_beds()`, `get_vitals()`, `get_appointments()`, `get_risk_scores()`, etc. Cache 30s.

2. **Analytics engine** (`hospital_analytics.py`)  
   - All calculations and data transformations. Calls repository only.  
   - **Public API for dashboard:**  
     - `compute_icu_occupancy()` — ICU total, occupied, rate, high_operational_risk  
     - `get_high_risk_patients(limit=20)` — readmission risk ≥ 0.6, display-ready columns  
     - `get_no_show_rates()` — department no-show aggregation  
     - `get_total_patients()`, `get_likely_no_shows()`, `get_admissions_trend()`, `get_patient_history()`, `get_patient_id_list()`  
   - Each function logs DataFrame sizes and column names (when DEBUG=1).  
   - **Standalone run for debugging:** `python -m hospital_analytics` or `DEBUG=1 .venv/bin/python hospital_analytics.py`

3. **Dashboard UI** (`app.py`)  
   - Thin visualization layer. Only renders Shiny components and calls analytics. No data processing or direct DB access.  
   - `safe_*()` wrappers call analytics and log errors; reactive calcs use `(df, error_msg)` and explicit UI error/empty messages.

- **Logging:** `dashboard_log.py` — `log()` (when DEBUG=1), `log_error()` (always), `log_empty()` (empty-result diagnostic)
- **Verification script:** `verify_supabase_data.py` — checks risk_scores and appointments and analytics outputs

---

## Key files

| File | Purpose |
|------|--------|
| `app.py` | Dashboard UI only: Shiny components, THEME, ICU_SEVERITY; calls analytics only |
| `database_connection.py` | Data repository: Supabase REST fetch, cache 30s, no business logic |
| `hospital_analytics.py` | Analytics engine: ICU occupancy, high-risk patients, no-show rates, trends, patient history; runnable standalone |
| `hospital_ai_agent.py` | LLM: operational summary, capacity alerts, explain risk, Q&A (uses analytics) |
| `risk_models.py` | Risk scoring helpers |
| `www/theme.css` | Dashboard theme (navbar, cards, value boxes, tables, buttons) |
| `dashboard_log.py` | Structured logging (DEBUG, log_error, log_empty) |
| `.env` | Supabase + optional OpenAI keys (not committed) |
| `run.sh` / `run.bat` | One-command run with .venv |

---

## Removed / changed (for context)

- **Command Center:** “High Risk Patients” and “Appointment Operations” table cards were removed from the main view (they were stuck loading); tables remain on their own nav tabs with reactive calcs and explicit error/empty UI.
- **ICU:** Long paragraph and single value_box replaced by the visual ICU capacity dashboard (metrics + bar + guidance).
- **Env:** Empty `OPENAI_BASE_URL` in .env was breaking the LLM client; app now forces default `https://api.openai.com/v1` when base URL is missing/invalid.

---

## Quick commands

```bash
cd hospital_dashboard
./run.sh                    # run dashboard
DEBUG=1 ./run.sh            # run with full pipeline logs
.venv/bin/python -m hospital_analytics    # run analytics layer standalone (debug)
.venv/bin/python verify_supabase_data.py  # verify Supabase + analytics
```

---

*Summary generated for handoff to a new chat. Update this file as the project evolves.*
