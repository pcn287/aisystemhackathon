# Hospital Patient Digital Twin — Dataset

This folder contains **synthetic hospital data** (CSVs) and scripts to **generate** or **import** it into Supabase for the Hospital Operations Command Center (Streamlit) dashboard.

---

## What’s in this folder

| Item | Description |
|------|-------------|
| **patients.csv** | 5,000 patients (demographics, chronic conditions, primary diagnosis) |
| **admissions.csv** | 12,000 inpatient admissions (dates, ICU flag, length of stay) |
| **appointments.csv** | 10,000 outpatient appointments (department, reminder, no-show) |
| **icu_beds.csv** | 50 ICU beds (occupancy, patient_id, expected discharge) |
| **risk_scores.csv** | 5,000 risk scores (readmission, ICU, no-show; 0–1) |
| **vitals.csv** | 120,000 vital-sign records (heart rate, BP, SpO2, etc.) |
| **CODEBOOK.md** | **Variable-level documentation** — every file and column, types, and how the app uses them |
| **generate_patient_twin_dataset.py** | Script to **generate** all CSVs from scratch (synthetic, reproducible) |
| **import_csv_to_supabase.py** | Script to **import** existing CSVs into Supabase (REST API) |
| **requirements.txt** | Python deps for generation/import (pandas, faker, requests, python-dotenv) |

---

## Background: Collecting or using the data

### Option A — Use the pre-generated CSVs

- The CSVs in this folder are **synthetic** and were produced by `generate_patient_twin_dataset.py`.
- They are **self-contained**: no real patient data; IDs (e.g. `P00001`), dates, and clinical fields are simulated with simple correlations (age, chronic conditions, distance, reminders) for demo and development.
- You can **use them as-is** for the Streamlit app after importing to Supabase (see below).

### Option B — Regenerate the dataset

If you need a fresh or modified dataset (e.g. different size or seed):

1. **Install dependencies** (from this folder or project root):
   ```bash
   pip install -r requirements.txt
   ```
   Requirements: `pandas`, `numpy`, `faker`, and standard library.

2. **Run the generator**:
   ```bash
   cd "Dataset for Hackathon"
   python generate_patient_twin_dataset.py
   ```
   This overwrites the six CSVs. Constants (e.g. `N_PATIENTS`, `N_ADMISSIONS`) are at the top of the script; you can change them and rerun.

3. **What the generator does:**  
   Builds patients with age, gender, insurance, smoking, BMI, chronic conditions, and primary diagnosis (with simple correlations). Then generates admissions (with ICU flag and length of stay), vitals (with COPD/ICU-linked variance), appointments (with no-show logic), 50 ICU beds (70–90% occupied), and risk_scores (readmission, ICU, no-show) per patient. All random seeds are fixed for reproducibility.

### Option C — Your own data

To use **your own** data:

1. **Schema:** Your tables must match what the app expects. Use **supabase_schema.sql** (in the repo root) as the reference; column names and types must align (see CODEBOOK.md for the exact variables and types).
2. **IDs:** Use a stable `patient_id` (and same IDs across admissions, appointments, risk_scores, vitals). The app uses `patient_id` for joins and drill-downs.
3. **Risk scores:** Store as 0.0–1.0 (or normalize in the app). The dashboard treats readmission_risk ≥ 0.6 as high risk and ≥ 0.8 as critical.
4. **Dates:** Use `YYYY-MM-DD` for dates; the app and import script assume date/timestamp columns as in the codebook.
5. **Optional:** Replace only some CSVs (e.g. keep patients + risk_scores, replace admissions). Ensure foreign keys and column names still match the schema and CODEBOOK.

---

## Using the data: Import into Supabase

The Streamlit dashboard reads from **Supabase** (PostgreSQL via REST). To load this dataset into Supabase:

### 1. Create the tables

In the [Supabase Dashboard](https://app.supabase.com) → **SQL Editor**, run the schema script from the **project root**:

```bash
# From repo root, the file is:
supabase_schema.sql
```

That file creates: `patients`, `admissions`, `appointments`, `icu_beds`, `risk_scores`, `vitals` (and indexes). Run it once per project.

### 2. Set environment variables

Create a `.env` file in the **project root** (or in `hospital_dashboard/`) with:

- `SUPABASE_URL` — your project URL (e.g. `https://xxxx.supabase.co`)
- `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_KEY` — service role key (Project Settings → API)

The import script loads `.env` from the parent of “Dataset for Hackathon” or current directory.

### 3. Run the import script

From the **Dataset for Hackathon** folder:

```bash
cd "Dataset for Hackathon"
pip install requests python-dotenv   # if not already installed
python import_csv_to_supabase.py
```

The script reads each CSV and POSTs rows in batches (500 per request) to the Supabase REST API. Order of import respects foreign keys: patients → admissions, appointments, icu_beds, risk_scores, then vitals. If `vitals.csv` is missing (e.g. you didn’t run the generator), the script will fail at `import_vitals()` — generate the dataset first or add a minimal `vitals.csv` that matches the schema.

### 4. Run the dashboard

From the repo root or `hospital_dashboard/`:

```bash
cd hospital_dashboard
streamlit run streamlit_dashboard.py
```

The app will read from Supabase using the same env vars.

---

## Variable and file reference

For **every file and variable** (names, types, meaning, examples, and how the app uses them), see:

- **[CODEBOOK.md](CODEBOOK.md)** — full dataset codebook.

For **app logic** (which functions read which tables and how), see:

- **hospital_dashboard/DOCUMENTATION.md** — module and function documentation.

---

## Summary

| Goal | Action |
|------|--------|
| Understand a column or file | Open **CODEBOOK.md** |
| Regenerate synthetic data | Run `generate_patient_twin_dataset.py` |
| Load CSVs into Supabase | Run `supabase_schema.sql`, then `import_csv_to_supabase.py` |
| Use your own data | Match **supabase_schema.sql** and **CODEBOOK.md**; keep `patient_id` and risk 0–1 |
