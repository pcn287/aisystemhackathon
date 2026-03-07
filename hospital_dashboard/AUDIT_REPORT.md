# AUDIT REPORT

## A. Data Contract Mismatches

1. **hospital_analytics.py** assumes `readmission_risk` is float 0.0–1.0; **database_connection.py** returns raw JSON — risk_scores may be string or 0–100 scale.
2. **hospital_analytics.py** uses `_safe_date_col` with candidates like `admission_date`, `discharge_date`, `appointment_date`; DB returns ISO date strings — no explicit normalization to `pd.Timestamp`/date in DB layer.
3. **hospital_analytics.py** `get_high_readmission_patients()` returns `pd.DataFrame()` with **no columns** when no match or empty; **app.py** and **hospital_ai_agent.py** expect columns e.g. `readmission_risk`, `patient_id` — downstream can KeyError or show wrong counts.
4. **hospital_analytics.py** `get_department_no_show_rates()` returns a DataFrame that may have `no_show_rate` or different rate column name; **app.py** infers `rate_col` — fragile if schema changes.
5. **hospital_analytics.py** assumes icu_beds has `occupied` or `status` or `patient_id`; **database_connection.py** does not guarantee column names.
6. **app.py** `r_discharge_pipeline()` uses `_safe_date_col(ready_df, ["patient_id", "patient"])` for patient ID (non-date); same helper used for both date and ID columns.

## B. Silent Failures

1. **app.py** `kpi_current()`: catches Exception and returns 0 for total, icu_pct, readmit, noshow — hides DB/analytics errors.
2. **app.py** `health_banner()`: try/except sets strain=0, icu_rate=readmit_rate=noshow_rate=0 — real errors not surfaced.
3. **app.py** `cmd_action_items()`: try/except returns text="" on any error — AI or data failure invisible.
4. **app.py** many render functions (alerts_feed, department_breakdown, noshow_summary_row, noshow_stats, etc.): try/except and return empty or placeholder — errors swallowed.
5. **hospital_ai_agent.py** `_call_llm()`: catches Exception and returns error string; retry path has bare `except Exception: pass` — second failure swallowed.
6. **hospital_analytics.py** `get_high_readmission_patients()`: returns empty `pd.DataFrame()` in multiple branches with no columns — callers get 0 count or KeyError later.
7. **app.py** `readmission_data()` / `noshow_data()`: return `(df, str(e))` on error; many UIs only check `df.empty`, not the error tuple.
8. **app.py** safe_* wrappers re-raise after logging, but callers (e.g. health_banner, gauge_readmit) catch and return defaults — user never sees error.

## C. Performance Problems

1. **database_connection.py** `_fetch_table()`: no .limit(); fetches entire table with pagination (5000 per page) — patients, admissions, vitals, appointments, icu_beds, risk_scores all unbounded.
2. **get_vitals()**: fetches full vitals table (comments mention 120k+ rows) — no limit.
3. **app.py** Command Center: **health_banner** calls safe_total_patients(), safe_icu_occupancy(), safe_high_readmission(100), safe_likely_no_shows() (4 calls). **cmd_action_items** calls safe_high_readmission(500) then **generate_operational_summary()** which internally calls get_total_patients, get_icu_occupancy, get_high_readmission_patients(500), get_likely_no_shows, get_admissions_trend(7), get_department_no_show_rates — **6+ DB-backed calls on every load**.
4. **kpi_current()** calls 4 safe_*; then **gauge_readmit**, **gauge_noshow**, **alerts_feed**, **department_breakdown** each call safe_* again — **duplicate fetches per render cycle**.
5. **generate_operational_summary()** and **answer_user_question()**: no caching; **block UI thread** while LLM runs (no timeout, no async).
6. **get_patient_history(patient_id)** calls get_patients(), get_admissions(), get_risk_scores() and get_vitals_for_patient() — 4 calls per patient; if used in a loop, N+1 pattern.

## D. Reactive Logic Bugs (app.py)

1. **cmd_action_items** is `@render.ui` with **no @reactive.event** — runs on every reactive invalidation and **calls AI on page load** (blocking).
2. **health_banner**, **gauge_readmit**, **gauge_noshow**, **alerts_feed**, **cmd_action_items**, **department_breakdown**, **noshow_summary_row**, **noshow_stats**, **noshow_patients_table**, **twin_***: call **safe_* or get_* directly** instead of reading from reactive.calc only — no caching, multiple DB hits per cycle.
3. **readmission_data()** uses **get_high_risk_patients(100)** directly (not safe_*); **noshow_data()** uses **get_no_show_rates()** — inconsistent with rest of app.
4. **reactive.poll**: current pattern `@reactive.poll(_poll_clock, 60)` and `_refreshed_at()` returns timestamp — correct; poll doesn’t hit DB.
5. **twin_ai_explanation**: already `@reactive.event(input.load_twin)` — good; only runs on button click.
6. **ai_answer**: `@reactive.event(input.ask_ai)` — good. No duplicate output IDs after prior fix (gauge_icu_tab2, icu_bed_grid_tab2).

## E. Data Logic Bugs

1. **KPI vs AI count**: KPI uses len(safe_high_readmission(limit=**100**)); cmd_action_items passes len(safe_high_readmission(limit=**500**)) as context; AI’s generate_operational_summary() calls get_high_readmission_patients(limit=**500**) — **same data for AI and context**, but **KPI shows cap at 100** — counts can differ (KPI “100” vs AI “500”).
2. **Readmission count**: get_high_readmission_patients returns **rows**; if risk_scores has **multiple rows per patient**, count is inflated — should use **.drop_duplicates(subset=['patient_id'])** before counting.
3. **Date comparisons**: analytics use pd.to_datetime(..., errors="coerce") and .dt.date — OK; app r_discharge_pipeline same — timestamp vs date mismatch possible if DB returns timezone-aware strings.
4. **Risk score scale**: no single normalization; if DB stores 0–100, threshold 0.6 would match nothing — need **normalize to 0.0–1.0** before threshold.
5. **Empty DataFrames**: get_high_readmission_patients returns `pd.DataFrame()` with **no columns**; readmission_summary_bar uses `df["readmission_risk"]` — **KeyError** when empty and columns missing. readmission_cards checks `"readmission_risk" in df.columns` — OK when columns present; empty DataFrame from analytics has no columns.

## F. Missing Error States

1. **readmission_summary_bar**: if readmission_data() returns df with no "readmission_risk" column (e.g. empty DataFrame from analytics), critical/high use df["readmission_risk"] — **KeyError**.
2. **readmission_dist_chart**: checks "readmission_risk" in df.columns — OK.
3. **trend_main_chart** / **trend_net_chart**: use trend_df(); if trend_df returns DataFrame with missing "date" or "admissions", **KeyError**.
4. **icu_stats_cards**: if r_trend() returns df without "admissions", df['admissions'] — **KeyError**.
5. **department_breakdown**: if dept_rates.empty we return; if dept_rates has rows but no numeric rate column, rate_col can be None and row.get(rate_col) — still works (returns "—"); if beds_df empty, unit_col None and beds_df[unit_col] not accessed when unit_col — OK. **dept_rates.columns[0]** when dept_col is None could fail if empty — already guarded by `if dept_rates.empty or dept_col is None`.
6. **noshow_bar_chart**: rate_col logic can yield non-existent column if df columns change — defensive but fragile.
7. **twin_vitals_chart** / **twin_admissions_chart**: hist.get("vitals") or hist.get("admissions") — empty DataFrame handled; num_cols/date_cols may be empty — handled with empty fig.
8. **gauge_icu** / **gauge_readmit** / **gauge_noshow**: try/except with default values — OK. No loading state; first load may show 0 until data arrives.
