# Dataset Codebook — Hospital Patient Digital Twin

This codebook describes every file and variable in the **Dataset for Hackathon** folder. Use it to understand, collect, or reuse the data.

---

## Overview

| File | Rows (approx) | Description |
|------|----------------|-------------|
| **patients.csv** | 5,000 | One row per patient; demographics and baseline clinical info. |
| **admissions.csv** | 12,000 | Inpatient admissions with dates, diagnosis, ICU flag, length of stay. |
| **appointments.csv** | 10,000 | Outpatient appointments with department, reminder, distance, no-show outcome. |
| **icu_beds.csv** | 50 | ICU beds with occupancy and expected discharge. |
| **risk_scores.csv** | 5,000 | One row per patient: readmission, ICU, and no-show risk (0–1). |
| **vitals.csv** | 120,000 | Time-stamped vital signs (heart rate, BP, SpO2, etc.) per patient. |

**Relationships:**  
`patients` is the central table. `admissions`, `appointments`, `risk_scores`, and `vitals` reference `patient_id`. `icu_beds` optionally references `patient_id` when occupied.

---

## 1. patients.csv

**Purpose:** Master list of patients and their demographic/clinical baseline.  
**Primary key:** `patient_id`.  
**Use in app:** Total patient count, drill-down lists, Patient Twin demographics, filters (age, diagnosis).

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **patient_id** | string | Unique patient identifier | `P00001`, `P05000` |
| **age** | integer | Age in years | 20–90; distribution skewed toward 40–70 |
| **gender** | string | Sex | `M`, `F` |
| **zip_code** | string | US ZIP code | From Faker; used for geography/location |
| **insurance_type** | string | Payer type | `Medicare`, `Private`, `Medicaid` (age-correlated) |
| **smoking_status** | boolean | Current smoker | `True` / `False`; ~15% True |
| **bmi** | numeric | Body mass index | 18–40; slightly skewed higher |
| **chronic_conditions** | string | Chronic condition category | `none`, `diabetes`, `hypertension`, `COPD`, `heart_failure` |
| **primary_diagnosis** | string | Primary diagnosis label | `pneumonia`, `COPD`, `heart_failure`, `diabetes`, `stroke`, `injury` |

**Correlations (synthetic):** Older age → more Medicare, more chronic conditions. Smoking → higher COPD. Higher BMI → higher diabetes. Chronic condition influences primary diagnosis.

---

## 2. admissions.csv

**Purpose:** Inpatient admission events: when and why the patient was admitted, whether ICU was required, length of stay.  
**Primary key:** `admission_id`.  
**Use in app:** Admissions/discharges trend, “today” counts, patient history, reference date for “today.”

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **admission_id** | string | Unique admission identifier | `A00001`, `A12000` |
| **patient_id** | string | FK to patients | Must exist in `patients.csv` |
| **admission_date** | date | Date of admission | `YYYY-MM-DD`; range ~2023-01 to 2024-08 |
| **discharge_date** | date | Date of discharge | `YYYY-MM-DD`; ≥ admission_date |
| **diagnosis_code** | string | Diagnosis code (e.g. ICD-10 style) | `ICD10-731`, `ICD10-602` |
| **admission_type** | string | Type of admission | `emergency`, `elective` (~60% emergency) |
| **icu_required** | boolean | Whether ICU was required | `True` / `False`; higher in emergency and COPD/heart_failure |
| **length_of_stay** | integer | Days in hospital | 1–14; older patients tend longer |
| **previous_admissions** | integer | Count of prior admissions (capped) | 0–5; used for readmission context |

**Correlations (synthetic):** Emergency and certain chronic conditions increase `icu_required`. Age influences length of stay.

---

## 3. appointments.csv

**Purpose:** Outpatient appointments: when, where, whether a reminder was sent, distance to hospital, and whether the patient no-showed.  
**Primary key:** `appointment_id`.  
**Use in app:** No-show rate by department, “likely no-shows” list, no-show trend, no_show_risk calibration.

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **appointment_id** | string | Unique appointment identifier | `APT00001`, `APT10000` |
| **patient_id** | string | FK to patients | Must exist in `patients.csv` |
| **appointment_date** | date | Scheduled date | `YYYY-MM-DD`; range 2024 |
| **department** | string | Clinic/department | `cardiology`, `pulmonology`, `oncology`, `orthopedics`, `general` |
| **appointment_time** | string/time | Scheduled time | `HH:MM` (e.g. `09:00`, `17:45`) |
| **reminder_sent** | boolean | Whether a reminder was sent | `True` / `False`; ~70% True; reduces no-show in logic |
| **distance_to_hospital** | integer | Distance (e.g. miles) to hospital | 1–60; higher → higher no-show in logic |
| **no_show** | boolean | Patient did not attend | `True` / `False`; used for department no-show rate and no_show_risk |

**Correlations (synthetic):** No-show probability increases with distance and younger age; decreases with reminder. Department used for aggregation only in this dataset.

---

## 4. icu_beds.csv

**Purpose:** Snapshot of ICU beds: which are occupied and by which patient, and expected discharge date.  
**Primary key:** `bed_id`.  
**Use in app:** ICU occupancy rate, bed grid, “ICU patients” drill-down.

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **bed_id** | string | Unique bed identifier | `ICU01`, `ICU50` |
| **ward** | string | Ward name | `ICU` (single ward in this dataset) |
| **occupied** | boolean | Whether the bed is occupied | `True` / `False`; typically 70–90% True in generator |
| **patient_id** | string | FK to patients (if occupied) | Null when `occupied` is False |
| **expected_discharge_date** | date | Planned discharge (if occupied) | `YYYY-MM-DD`; can be used for discharge planning |

**Note:** This is a point-in-time snapshot. The dashboard uses it for current occupancy only (no historical bed states).

---

## 5. risk_scores.csv

**Purpose:** One row per patient with model-produced risk scores (0–1) for readmission, ICU need, and appointment no-show.  
**Primary key:** `patient_id`.  
**Use in app:** High readmission list (e.g. ≥0.6), root-cause analysis, strain metrics, Patient Twin risk display, no-show risk for “likely no-shows.”

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **patient_id** | string | Unique patient; FK to patients | One row per patient |
| **readmission_risk** | numeric | Probability of 30-day readmission | 0.0–1.0; dashboard flags ≥0.6 as high, ≥0.8 as critical |
| **icu_risk** | numeric | Probability of needing ICU | 0.0–1.0; used for ICU risk views if needed |
| **no_show_risk** | numeric | Probability of missing next appointment | 0.0–1.0; used for “likely no-shows” and department logic |
| **risk_last_updated** | timestamp | When scores were last updated | `YYYY-MM-DD HH:MM:SS`; for auditing only in app |

**Correlations (synthetic):** Readmission risk increases with age. ICU risk increases with COPD/heart_failure. No-show risk increases with average distance to hospital (from appointments).

---

## 6. vitals.csv

**Purpose:** Time-series vital signs per patient. Used for Patient Digital Twin and any vitals-based logic.  
**Primary key:** `record_id`.  
**Use in app:** Patient Twin vitals chart, LLM patient context (if passed to AI).

| Variable | Type | Description | Example / Notes |
|----------|------|-------------|------------------|
| **record_id** | integer | Unique vitals record ID | 1 to ~120,000 |
| **patient_id** | string | FK to patients | Multiple rows per patient (~24 per patient in generator) |
| **timestamp** | datetime | When the vital was recorded | `YYYY-MM-DD HH:MM:SS`; range over ~1 year |
| **heart_rate** | integer | Heart rate (bpm) | 60–130; ICU patients have higher variance in generator |
| **systolic_bp** | integer | Systolic blood pressure (mmHg) | 90–180 |
| **respiratory_rate** | integer | Breaths per minute | 12–30 |
| **oxygen_saturation** | integer | SpO2 (%) | 85–100; COPD patients slightly lower in generator |
| **temperature** | numeric | Body temperature (°C) | 36–39 |

**Correlations (synthetic):** COPD → slightly lower oxygen saturation; ICU (from admissions) → higher variance in vitals.

---

## Data types and conventions

- **Dates:** `YYYY-MM-DD`.  
- **Times / timestamps:** `HH:MM` or `YYYY-MM-DD HH:MM:SS` as in the codebook table.  
- **Booleans in CSV:** `True` / `False` (Python-style); import script maps `true`/`1`/`yes` to True.  
- **Risk scores:** Always 0.0–1.0 in this dataset. If your pipeline produces 0–100, normalize before use or in the app.  
- **Missing values:** Empty string or null; app and import handle nulls.

---

## Supabase table mapping

| CSV file | Supabase table | Notes |
|----------|----------------|------|
| patients.csv | **patients** | Primary key: `patient_id` |
| admissions.csv | **admissions** | FK: `patient_id` → patients |
| appointments.csv | **appointments** | FK: `patient_id` → patients |
| icu_beds.csv | **icu_beds** | FK: `patient_id` → patients (nullable) |
| risk_scores.csv | **risk_scores** | One-to-one with patients |
| vitals.csv | **vitals** | FK: `patient_id` → patients |

Schema (CREATE TABLE statements) is in the repo root: **supabase_schema.sql**. Run it in the Supabase SQL Editor before importing.

---

## How the app uses these variables

- **Strain / KPIs:** `get_system_strain()` uses patients (count), icu_beds (occupancy), risk_scores (high readmission count), appointments (likely no-shows), admissions (today’s admissions/discharges, reference date).  
- **Trends:** Admissions → `admission_date`, `discharge_date`. Appointments → `appointment_date`, `no_show`. Risk scores → readmission_risk for “high-risk” counts by day.  
- **Readmission Risk tab:** `risk_scores.readmission_risk`, merged with patients (diagnosis, department if present).  
- **No-Show tab:** `appointments.department`, `appointments.no_show`, and `risk_scores.no_show_risk`.  
- **Patient Twin:** `get_patient_history(patient_id)` merges patients, admissions, risk_scores, and vitals (via `get_vitals_for_patient`).

For function-level detail, see **hospital_dashboard/DOCUMENTATION.md**.
