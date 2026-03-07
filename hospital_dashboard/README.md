# Patient Digital Twin Hospital Intelligence Dashboard

Hospital analytics platform using Supabase data, prediction logic, an LLM reasoning layer, and a Shiny for Python dashboard.

## Setup

1. **Create and activate a virtual environment**

   From the project root, or from `hospital_dashboard`:

   ```bash
   cd hospital_dashboard
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Environment variables**

   Copy `.env.example` to `.env` in the `hospital_dashboard` directory and fill in:

   - **Required for Supabase (database):**
     - `SUPABASE_URL` – your Supabase project URL
     - `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_KEY` – your Supabase key

   - **Optional for LLM (AI Assistant, summaries, explanations):**
     - `OPENAI_API_KEY` or `LLM_API_KEY` – API key for an OpenAI-compatible API
     - `OPENAI_BASE_URL` – base URL if using a different provider (leave unset for OpenAI cloud)
     - `LLM_MODEL` – model name (default: `gpt-4o-mini`)

   Example (Unix/macOS):

   ```bash
   export SUPABASE_URL="https://xxxx.supabase.co"
   export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
   export OPENAI_API_KEY="sk-..."
   ```

   Or use a `.env` file in `hospital_dashboard/` (do not commit it).  
   `.venv` and `.env` are in `.gitignore` and will not be committed.

## Debugging empty tables (High Risk Patients / Appointment Operations)

If the **High Risk Patients** or **Appointment Operations** panels show loading or no data:

1. **Verify Supabase data** (from `hospital_dashboard`):
   ```bash
   .venv/bin/python verify_supabase_data.py
   ```
   This checks `risk_scores` (column `readmission_risk`) and `appointments` (columns `department`, `no_show`).

2. **Enable debug logging** to see the full data pipeline (Supabase query results, dataframe shapes, filter results):
   ```bash
   DEBUG=1 ./run.sh
   ```
   Logs are structured by stage: `[Supabase]`, `[HighRisk]`, `[NoShow]`, `[Shiny]`. Errors are always printed (even without DEBUG). Empty results print a one-line diagnostic; set `DEBUG=1` for full pipeline logs.

3. **Schema**: Tables must have:
   - `risk_scores`: `patient_id`, `readmission_risk` (numeric, ≥ 0.6 for high risk)
   - `appointments`: `department` (or column containing "department"), `no_show` (bool) or `status`/`outcome`

## Run the dashboard

From the `hospital_dashboard` directory, use the run script (uses `.venv` automatically; no need to activate):

```bash
./run.sh
```

On Windows: double-click `run.bat` or run `run.bat` in a terminal.

Then open the URL shown (e.g. http://127.0.0.1:8000).

**Alternative** (with venv already activated):

```bash
shiny run app.py
```

Options (pass after `./run.sh`):

- `./run.sh --reload` – auto-reload on file changes  
- `./run.sh --launch-browser` – open browser automatically  

## Project structure

| File | Layer | Description |
|------|--------|-------------|
| `database_connection.py` | 1 – Data access | Supabase client; `get_patients()`, `get_admissions()`, etc. |
| `hospital_analytics.py` | 2 – Analytics | KPIs, ICU occupancy, readmission/no-show metrics, patient history |
| `risk_models.py` | 3 – Prediction | `calculate_readmission_risk()`, `calculate_icu_risk()`, `calculate_no_show_risk()` |
| `hospital_ai_agent.py` | 4 – LLM | `generate_operational_summary()`, `explain_patient_risk()`, `answer_user_question()` |
| `app.py` | 5 – Dashboard | Shiny UI: Summary, ICU, Readmission, No-Show, Patient Twin, Trends, AI Assistant |

## Hospital system assumptions

The dashboard is designed for a **mid-size regional healthcare system** with these assumptions:

1. **Profile** – ~5000 patients; 250–300 beds; **50 ICU beds**; 24/7 ED; departments: Cardiology, Pulmonology, Oncology, Orthopedics, General Medicine.
2. **Patients** – Age mix 20–40 (20%), 40–65 (40%), 65–90 (40%); chronic conditions: hypertension, diabetes, COPD, heart failure; older and chronically ill patients have higher hospitalization/readmission risk.
3. **ICU** – Typical occupancy 70–90%. **Occupancy ≥ 90% = high operational risk** (used for dashboard alerts).
4. **Admissions** – Emergency (via ER, more ICU need) and elective (scheduled); typical stay 2–7 days, severe cases >10 days.
5. **Readmission** – 30-day readmission tracked; baseline rate 10–20%. **Patients with predicted risk ≥ 0.6 are flagged** in the system.
6. **Appointments** – Outpatient by department; typical no-show 10–25%; higher no-show with long travel distance, younger patients, no reminder.
7. **Vitals** – Heart rate, blood pressure, respiratory rate, oxygen saturation, body temperature; abnormal patterns (e.g. SpO₂ &lt; 92%, HR &gt; 110 bpm) inform the digital twin.
8. **Digital twin** – Per-patient profile: demographics, history, vitals, admissions, risk predictions; updated as new data arrives.
9. **Decision support** – Dashboard answers: highest readmission risk, ICU capacity limits, likely no-shows, who needs extra monitoring.
10. **AI assistant** – Interprets risk scores, summarizes trends, suggests actions; **does not generate raw predictions**; all answers from database/analytics only.

## Database assumptions

The Supabase database is assumed to have these tables (with existing data):

- `patients` – e.g. `patient_id`, demographics (age, conditions, etc.)
- `admissions` – e.g. `patient_id`, `admission_date`, `discharge_date`, `department`, admission_type (emergency/elective)
- `vitals` – e.g. `patient_id`, timestamps, heart_rate, blood_pressure, respiratory_rate, oxygen_saturation, temperature
- `appointments` – e.g. `patient_id`, `appointment_date`, `department`, `status` (no-show/completed/etc.)
- `icu_beds` – e.g. `bed_id`, `patient_id`, `occupied` or `status`
- `risk_scores` – e.g. `patient_id`, `score_type` (readmission/no_show/icu), `value` or `score`

Column names are inferred where possible; analytics may need small adjustments if your schema differs.
