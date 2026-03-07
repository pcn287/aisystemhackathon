# Dataset for Hackathon — README & Codebook

One place for the **hospital dataset**: what each file and variable is, and how to collect or use the data with the Hospital Operations Command Center (Streamlit) dashboard.

---

## What’s in this folder

| Item | Description |
|------|-------------|
| **README.md** (this file) | Dataset overview, codebook (every file & variable), and how to generate/import data |
| **generate_patient_twin_dataset.py** | Generates all six CSVs from scratch (synthetic, reproducible) |
| **import_csv_to_supabase.py** | Imports the CSVs into Supabase (REST API) |
| **requirements.txt** | Python deps for generation/import (pandas, numpy, faker, requests, python-dotenv) |

No CSV files are stored in the repo. Generate them when needed (see below), then import into Supabase. The dashboard reads only from Supabase.

---

## Background: Collecting or using the data

### Option A — Generate then import (recommended)

1. **Install dependencies:**
   ```bash
   cd "Dataset for Hackathon"
   pip install -r requirements.txt
   ```

2. **Generate the CSVs:**
   ```bash
   python generate_patient_twin_dataset.py
   ```
   This creates: `patients.csv` (5,000), `admissions.csv` (12,000), `appointments.csv` (10,000), `icu_beds.csv` (50), `risk_scores.csv` (5,000), `vitals.csv` (120,000). All data is synthetic (no real patients). Seeds are fixed for reproducibility.

3. **Import into Supabase:** Run `supabase_schema.sql` in Supabase SQL Editor once, set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`, then:
   ```bash
   python import_csv_to_supabase.py
   ```

### Option B — Your own data

- Match the **schema** in **supabase_schema.sql** (repo root). Column names and types must align with the codebook below.
- Use a stable `patient_id` everywhere. Risk scores: 0.0–1.0 (dashboard treats readmission_risk ≥ 0.6 as high, ≥ 0.8 as critical).
- Dates: `YYYY-MM-DD`; timestamps: `YYYY-MM-DD HH:MM:SS`.

---

## Using the data: Import into Supabase

1. **Create tables:** Supabase Dashboard → SQL Editor → run **supabase_schema.sql** (from repo root).
2. **Environment:** In project root (or `hospital_dashboard/`), create `.env` with `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_KEY`).
3. **Generate CSVs** (if not present): `python generate_patient_twin_dataset.py`
4. **Import:** From this folder, run `python import_csv_to_supabase.py`. Order: patients → admissions → appointments → icu_beds → risk_scores → vitals.
5. **Run dashboard:** `cd hospital_dashboard && streamlit run streamlit_dashboard.py`

---

## Codebook — Files and variables

### Overview

| File | Rows (approx) | Description |
|------|----------------|-------------|
| **patients.csv** | 5,000 | One row per patient; demographics and baseline clinical info. |
| **admissions.csv** | 12,000 | Inpatient admissions with dates, diagnosis, ICU flag, length of stay. |
| **appointments.csv** | 10,000 | Outpatient appointments with department, reminder, distance, no-show outcome. |
| **icu_beds.csv** | 50 | ICU beds with occupancy and expected discharge. |
| **risk_scores.csv** | 5,000 | One row per patient: readmission, ICU, and no-show risk (0–1). |
| **vitals.csv** | 120,000 | Time-stamped vital signs (heart rate, BP, SpO2, etc.) per patient. |

**Relationships:** `patients` is the central table. `admissions`, `appointments`, `risk_scores`, and `vitals` reference `patient_id`. `icu_beds` optionally references `patient_id` when occupied.

---

### 1. patients.csv

**Purpose:** Master list of patients. **Primary key:** `patient_id`. **Use in app:** Total patient count, drill-down lists, Patient Twin demographics, filters.

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **patient_id** | string | Unique patient identifier | `P00001`, `P05000` |
| **age** | integer | Age in years | 20–90; skewed toward 40–70 |
| **gender** | string | Sex | `M`, `F` |
| **zip_code** | string | US ZIP code | Geography/location |
| **insurance_type** | string | Payer type | `Medicare`, `Private`, `Medicaid` (age-correlated) |
| **smoking_status** | boolean | Current smoker | ~15% True |
| **bmi** | numeric | Body mass index | 18–40 |
| **chronic_conditions** | string | Chronic condition | `none`, `diabetes`, `hypertension`, `COPD`, `heart_failure` |
| **primary_diagnosis** | string | Primary diagnosis | `pneumonia`, `COPD`, `heart_failure`, `diabetes`, `stroke`, `injury` |

**Synthetic logic:** Older age → more Medicare, more chronic conditions. Smoking → higher COPD. Higher BMI → higher diabetes.

---

### 2. admissions.csv

**Purpose:** Inpatient admission events. **Primary key:** `admission_id`. **Use in app:** Admissions/discharges trend, “today” counts, patient history, reference date.

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **admission_id** | string | Unique admission identifier | `A00001`, `A12000` |
| **patient_id** | string | FK to patients | Must exist in patients |
| **admission_date** | date | Date of admission | `YYYY-MM-DD` |
| **discharge_date** | date | Date of discharge | ≥ admission_date |
| **diagnosis_code** | string | Diagnosis code (e.g. ICD-10) | `ICD10-731`, `ICD10-602` |
| **admission_type** | string | Type of admission | `emergency`, `elective` (~60% emergency) |
| **icu_required** | boolean | Whether ICU was required | Higher in emergency, COPD/heart_failure |
| **length_of_stay** | integer | Days in hospital | 1–14 |
| **previous_admissions** | integer | Prior admissions (capped) | 0–5 |

---

### 3. appointments.csv

**Purpose:** Outpatient appointments. **Primary key:** `appointment_id`. **Use in app:** No-show rate by department, “likely no-shows,” no-show trend.

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **appointment_id** | string | Unique appointment identifier | `APT00001` |
| **patient_id** | string | FK to patients | Must exist in patients |
| **appointment_date** | date | Scheduled date | `YYYY-MM-DD` |
| **department** | string | Clinic/department | `cardiology`, `pulmonology`, `oncology`, `orthopedics`, `general` |
| **appointment_time** | string/time | Scheduled time | `HH:MM` |
| **reminder_sent** | boolean | Reminder sent | ~70% True; reduces no-show in logic |
| **distance_to_hospital** | integer | Distance (e.g. miles) | 1–60; higher → higher no-show |
| **no_show** | boolean | Patient did not attend | Used for department no-show rate |

---

### 4. icu_beds.csv

**Purpose:** Snapshot of ICU beds. **Primary key:** `bed_id`. **Use in app:** ICU occupancy rate, bed grid, “ICU patients” drill-down.

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **bed_id** | string | Unique bed identifier | `ICU01`, `ICU50` |
| **ward** | string | Ward name | `ICU` |
| **occupied** | boolean | Bed occupied | Typically 70–90% True in generator |
| **patient_id** | string | FK to patients (if occupied) | Null when not occupied |
| **expected_discharge_date** | date | Planned discharge (if occupied) | `YYYY-MM-DD` |

Point-in-time snapshot; dashboard uses it for current occupancy only.

---

### 5. risk_scores.csv

**Purpose:** One row per patient with risk scores (0–1). **Primary key:** `patient_id`. **Use in app:** High readmission list (≥0.6), root-cause analysis, strain metrics, Patient Twin, no-show risk.

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **patient_id** | string | Unique patient; FK to patients | One row per patient |
| **readmission_risk** | numeric | Probability of 30-day readmission | 0.0–1.0; ≥0.6 high, ≥0.8 critical |
| **icu_risk** | numeric | Probability of needing ICU | 0.0–1.0 |
| **no_show_risk** | numeric | Probability of missing next appointment | 0.0–1.0 |
| **risk_last_updated** | timestamp | When scores were updated | `YYYY-MM-DD HH:MM:SS` |

**Synthetic logic:** Readmission ↑ with age. ICU risk ↑ with COPD/heart_failure. No-show risk ↑ with distance.

---

### 6. vitals.csv

**Purpose:** Time-series vital signs per patient. **Primary key:** `record_id`. **Use in app:** Patient Twin vitals chart, LLM patient context.

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **record_id** | integer | Unique vitals record ID | 1 to ~120,000 |
| **patient_id** | string | FK to patients | ~24 rows per patient in generator |
| **timestamp** | datetime | When recorded | `YYYY-MM-DD HH:MM:SS` |
| **heart_rate** | integer | Heart rate (bpm) | 60–130 |
| **systolic_bp** | integer | Systolic BP (mmHg) | 90–180 |
| **respiratory_rate** | integer | Breaths per minute | 12–30 |
| **oxygen_saturation** | integer | SpO2 (%) | 85–100; COPD slightly lower |
| **temperature** | numeric | Body temperature (°C) | 36–39 |

---

## Data types and conventions

- **Dates:** `YYYY-MM-DD`. **Timestamps:** `YYYY-MM-DD HH:MM:SS` or `HH:MM`.
- **Booleans in CSV:** `True` / `False`; import script also accepts `true`/`1`/`yes`.
- **Risk scores:** 0.0–1.0. If your pipeline uses 0–100, normalize before use.
- **Missing values:** Empty or null; app and import handle nulls.

---

## Supabase table mapping

| CSV file | Supabase table | Notes |
|----------|----------------|-------|
| patients.csv | **patients** | Primary key: `patient_id` |
| admissions.csv | **admissions** | FK: `patient_id` → patients |
| appointments.csv | **appointments** | FK: `patient_id` → patients |
| icu_beds.csv | **icu_beds** | FK: `patient_id` → patients (nullable) |
| risk_scores.csv | **risk_scores** | One-to-one with patients |
| vitals.csv | **vitals** | FK: `patient_id` → patients |

Schema: **supabase_schema.sql** (repo root). Run it in Supabase SQL Editor before importing.

---

## How the app uses these variables

- **Strain / KPIs:** patients (count), icu_beds (occupancy), risk_scores (high readmission count), appointments (likely no-shows), admissions (today’s counts, reference date).
- **Trends:** admission_date, discharge_date, appointment_date, no_show, readmission_risk for daily series.
- **Readmission Risk tab:** risk_scores.readmission_risk merged with patients (diagnosis, etc.).
- **No-Show tab:** appointments.department, appointments.no_show, risk_scores.no_show_risk.
- **Patient Twin:** get_patient_history() merges patients, admissions, risk_scores, vitals.

App logic details: **hospital_dashboard/DOCUMENTATION.md**.

---

## Summary

| Goal | Action |
|------|--------|
| Understand a column or file | Use the **Codebook** section above in this README |
| Generate synthetic data | Run `generate_patient_twin_dataset.py` |
| Load data into Supabase | Run `supabase_schema.sql`, then `import_csv_to_supabase.py` |
| Use your own data | Match **supabase_schema.sql** and codebook; keep `patient_id` and risk 0–1 |
