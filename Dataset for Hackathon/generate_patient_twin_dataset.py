#!/usr/bin/env python3
"""
Generate a realistic synthetic dataset for a hospital Patient Digital Twin system.
Uses pandas, numpy, faker, and random with organic correlations similar to real healthcare data.
"""

import pandas as pd
import numpy as np
from faker import Faker
import random
from datetime import datetime, timedelta
from collections import defaultdict

# Initialize
fake = Faker()
Faker.seed(42)
random.seed(42)
np.random.seed(42)

# Constants
N_PATIENTS = 5000
N_ADMISSIONS = 12000
N_VITALS = 120000
N_APPOINTMENTS = 10000
N_ICU_BEDS = 50

# Chronic conditions and diagnoses for correlation logic
CHRONIC_CONDITIONS = ["diabetes", "hypertension", "COPD", "heart_failure", "none"]
PRIMARY_DIAGNOSES = ["pneumonia", "COPD", "heart_failure", "diabetes", "stroke", "injury"]
DEPARTMENTS = ["cardiology", "pulmonology", "oncology", "orthopedics", "general"]


def generate_patients():
    """Generate 5000 patients with realistic correlations."""
    patients = []
    patient_ids = [f"P{i:05d}" for i in range(1, N_PATIENTS + 1)]

    for i, pid in enumerate(patient_ids):
        # Age: more middle-aged and elderly (beta-like distribution)
        age_raw = np.random.beta(2.5, 2)  # Skew toward 40-70
        age = int(20 + age_raw * 70)  # 20-90 range
        age = min(90, max(20, age))

        # Gender
        gender = random.choice(["M", "F"])

        # ZIP code (US format)
        zip_code = fake.zipcode()

        # Insurance: patients over 65 more likely to have Medicare
        if age >= 65:
            insurance = random.choices(
                ["Medicare", "Private", "Medicaid"],
                weights=[0.65, 0.25, 0.10]
            )[0]
        else:
            insurance = random.choices(
                ["Private", "Medicaid", "Medicare"],
                weights=[0.55, 0.30, 0.15]
            )[0]

        # Smoking: ~15% smokers
        smoking_status = random.random() < 0.15

        # BMI: 18-40, slightly skewed toward higher values
        bmi = round(18 + np.random.beta(2, 2) * 22, 1)
        bmi = min(40, max(18, bmi))

        # Chronic conditions: older patients more likely
        age_factor = (age - 20) / 70  # 0 to 1
        p_none = 0.4 - age_factor * 0.25  # Older = less "none"
        p_none = max(0.1, p_none)

        if random.random() < p_none:
            chronic = "none"
        else:
            chronic = random.choices(
                ["diabetes", "hypertension", "COPD", "heart_failure"],
                weights=[0.25, 0.35, 0.20, 0.20]
            )[0]

        # Smokers more likely to have COPD
        if smoking_status and chronic != "none":
            chronic = "COPD" if random.random() < 0.6 else chronic
        elif smoking_status:
            chronic = "COPD" if random.random() < 0.4 else "none"

        # Higher BMI correlated with diabetes
        if bmi > 30 and chronic != "none":
            chronic = "diabetes" if random.random() < 0.5 else chronic
        elif bmi > 30:
            chronic = "diabetes" if random.random() < 0.35 else chronic

        # Primary diagnosis - correlate with chronic conditions
        if chronic == "COPD":
            primary = random.choices(
                ["COPD", "pneumonia", "heart_failure"],
                weights=[0.6, 0.25, 0.15]
            )[0]
        elif chronic == "heart_failure":
            primary = random.choices(
                ["heart_failure", "COPD", "pneumonia"],
                weights=[0.6, 0.2, 0.2]
            )[0]
        elif chronic == "diabetes":
            primary = random.choices(
                ["diabetes", "pneumonia", "heart_failure", "stroke"],
                weights=[0.5, 0.2, 0.15, 0.15]
            )[0]
        elif chronic == "hypertension":
            primary = random.choices(
                ["stroke", "heart_failure", "diabetes", "pneumonia"],
                weights=[0.3, 0.3, 0.2, 0.2]
            )[0]
        else:
            primary = random.choice(PRIMARY_DIAGNOSES)

        patients.append({
            "patient_id": pid,
            "age": age,
            "gender": gender,
            "zip_code": zip_code,
            "insurance_type": insurance,
            "smoking_status": smoking_status,
            "bmi": bmi,
            "chronic_conditions": chronic,
            "primary_diagnosis": primary,
        })

    return pd.DataFrame(patients)


def generate_admissions(patients_df):
    """Generate 12000 admissions with patient references and realistic rules."""
    patient_ids = patients_df["patient_id"].tolist()
    patient_ages = dict(zip(patients_df["patient_id"], patients_df["age"]))
    patient_chronic = dict(zip(patients_df["patient_id"], patients_df["chronic_conditions"]))
    patient_primary = dict(zip(patients_df["patient_id"], patients_df["primary_diagnosis"]))

    admissions = []
    patient_admission_counts = defaultdict(int)

    base_date = datetime(2023, 1, 1)
    diagnosis_codes = [f"ICD10-{random.randint(100, 999)}" for _ in range(50)]

    for i in range(1, N_ADMISSIONS + 1):
        aid = f"A{i:05d}"
        patient_id = random.choice(patient_ids)
        age = patient_ages[patient_id]
        chronic = patient_chronic[patient_id]
        primary = patient_primary[patient_id]

        previous = patient_admission_counts[patient_id]
        patient_admission_counts[patient_id] += 1

        # Admission type: ~60% emergency
        is_emergency = random.random() < 0.6

        # Length of stay: older patients tend to stay longer (1-14 days)
        age_factor = (age - 20) / 70
        base_los = 2 + age_factor * 5  # 2-7 base
        los = int(np.random.exponential(base_los) + 1)
        los = min(14, max(1, los))

        # ICU required: emergency more likely, COPD/heart_failure more likely
        p_icu = 0.15
        if is_emergency:
            p_icu += 0.25
        if chronic in ["COPD", "heart_failure"]:
            p_icu += 0.2
        icu_required = random.random() < min(0.9, p_icu)

        admission_date = base_date + timedelta(days=random.randint(0, 600))
        discharge_date = admission_date + timedelta(days=los)

        admissions.append({
            "admission_id": aid,
            "patient_id": patient_id,
            "admission_date": admission_date.strftime("%Y-%m-%d"),
            "discharge_date": discharge_date.strftime("%Y-%m-%d"),
            "diagnosis_code": random.choice(diagnosis_codes),
            "admission_type": "emergency" if is_emergency else "elective",
            "icu_required": icu_required,
            "length_of_stay": los,
            "previous_admissions": min(previous, 5),
        })

    return pd.DataFrame(admissions)


def generate_vitals(patients_df, admissions_df):
    """Generate ~120000 vitals records (~24 per patient for 5000 patients)."""
    patient_ids = patients_df["patient_id"].tolist()
    patient_chronic = dict(zip(patients_df["patient_id"], patients_df["chronic_conditions"]))

    # Get patients who had ICU
    icu_patients = set(
        admissions_df[admissions_df["icu_required"]]["patient_id"].unique()
    )

    vitals = []
    record_id = 1
    records_per_patient = N_VITALS // N_PATIENTS  # 24

    base_date = datetime(2023, 6, 1)

    for patient_id in patient_ids:
        chronic = patient_chronic.get(patient_id, "none")
        in_icu = patient_id in icu_patients

        # COPD: slightly lower oxygen saturation
        o2_offset = -3 if chronic == "COPD" else 0
        # ICU: more abnormal vitals (wider variance)
        variance_mult = 1.5 if in_icu else 1.0

        for _ in range(records_per_patient):
            ts = base_date + timedelta(
                days=random.randint(0, 365),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )

            heart_rate = int(75 + np.random.normal(0, 12 * variance_mult))
            heart_rate = min(130, max(60, heart_rate))

            systolic_bp = int(120 + np.random.normal(0, 18 * variance_mult))
            systolic_bp = min(180, max(90, systolic_bp))

            resp_rate = int(16 + np.random.normal(0, 4 * variance_mult))
            resp_rate = min(30, max(12, resp_rate))

            oxygen_sat = int(96 + o2_offset + np.random.normal(0, 3 * variance_mult))
            oxygen_sat = min(100, max(85, oxygen_sat))

            temp = round(36.5 + np.random.normal(0, 0.5 * variance_mult), 1)
            temp = min(39, max(36, temp))

            vitals.append({
                "record_id": record_id,
                "patient_id": patient_id,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "heart_rate": heart_rate,
                "systolic_bp": systolic_bp,
                "respiratory_rate": resp_rate,
                "oxygen_saturation": oxygen_sat,
                "temperature": temp,
            })
            record_id += 1

    # Add remaining records to reach 120000 if needed
    while len(vitals) < N_VITALS:
        patient_id = random.choice(patient_ids)
        chronic = patient_chronic.get(patient_id, "none")
        in_icu = patient_id in icu_patients
        o2_offset = -3 if chronic == "COPD" else 0
        variance_mult = 1.5 if in_icu else 1.0

        ts = base_date + timedelta(
            days=random.randint(0, 365),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
        vitals.append({
            "record_id": record_id,
            "patient_id": patient_id,
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "heart_rate": min(130, max(60, int(75 + np.random.normal(0, 12 * variance_mult)))),
            "systolic_bp": min(180, max(90, int(120 + np.random.normal(0, 18 * variance_mult)))),
            "respiratory_rate": min(30, max(12, int(16 + np.random.normal(0, 4 * variance_mult)))),
            "oxygen_saturation": min(100, max(85, int(96 + o2_offset + np.random.normal(0, 3 * variance_mult)))),
            "temperature": round(min(39, max(36, 36.5 + np.random.normal(0, 0.5 * variance_mult))), 1),
        })
        record_id += 1

    return pd.DataFrame(vitals)


def generate_appointments(patients_df):
    """Generate 10000 appointments with no-show and reminder logic."""
    patient_ids = patients_df["patient_id"].tolist()
    patient_ages = dict(zip(patients_df["patient_id"], patients_df["age"]))

    appointments = []
    base_date = datetime(2024, 1, 1)

    for i in range(1, N_APPOINTMENTS + 1):
        aid = f"APT{i:05d}"
        patient_id = random.choice(patient_ids)
        age = patient_ages[patient_id]

        appointment_date = base_date + timedelta(days=random.randint(0, 365))
        department = random.choice(DEPARTMENTS)
        hour = random.randint(8, 17)
        minute = random.choice([0, 15, 30, 45])
        appointment_time = f"{hour:02d}:{minute:02d}"

        reminder_sent = random.random() < 0.7
        distance = random.randint(1, 60)

        # No-show: longer distance increases, reminder reduces, younger slightly higher
        p_noshow = 0.08
        p_noshow += (distance / 60) * 0.15  # Up to +15% for long distance
        if not reminder_sent:
            p_noshow += 0.12
        if age < 40:
            p_noshow += 0.05
        no_show = random.random() < min(0.5, p_noshow)

        appointments.append({
            "appointment_id": aid,
            "patient_id": patient_id,
            "appointment_date": appointment_date.strftime("%Y-%m-%d"),
            "department": department,
            "appointment_time": appointment_time,
            "reminder_sent": reminder_sent,
            "distance_to_hospital": distance,
            "no_show": no_show,
        })

    return pd.DataFrame(appointments)


def generate_icu_beds(admissions_df, patients_df):
    """Generate 50 ICU beds, 70-90% occupied."""
    patient_ids = patients_df["patient_id"].tolist()
    n_occupied = random.randint(int(N_ICU_BEDS * 0.7), int(N_ICU_BEDS * 0.9))

    beds = []
    base_date = datetime(2024, 3, 1)

    for i in range(1, N_ICU_BEDS + 1):
        bed_id = f"ICU{i:02d}"
        occupied = i <= n_occupied
        patient_id = random.choice(patient_ids) if occupied else None
        expected_discharge = (base_date + timedelta(days=random.randint(0, 7))).strftime("%Y-%m-%d") if occupied else None

        beds.append({
            "bed_id": bed_id,
            "ward": "ICU",
            "occupied": occupied,
            "patient_id": patient_id,
            "expected_discharge_date": expected_discharge,
        })

    return pd.DataFrame(beds)


def generate_risk_scores(patients_df, appointments_df):
    """Generate risk scores for each patient with realistic correlations."""
    patient_ages = dict(zip(patients_df["patient_id"], patients_df["age"]))
    patient_chronic = dict(zip(patients_df["patient_id"], patients_df["chronic_conditions"]))

    # Average distance per patient from appointments
    patient_distances = appointments_df.groupby("patient_id")["distance_to_hospital"].mean().to_dict()

    base_date = datetime(2024, 3, 6)

    risk_scores = []
    for _, row in patients_df.iterrows():
        pid = row["patient_id"]
        age = row["age"]
        chronic = row["chronic_conditions"]
        distance = patient_distances.get(pid, 15)

        # Readmission risk: age increases
        readmission_risk = 0.2 + (age - 20) / 70 * 0.5 + np.random.normal(0, 0.1)
        readmission_risk = min(1, max(0, readmission_risk))

        # ICU risk: COPD and heart failure increase
        icu_risk = 0.15
        if chronic in ["COPD", "heart_failure"]:
            icu_risk += 0.35
        icu_risk += np.random.normal(0, 0.1)
        icu_risk = min(1, max(0, icu_risk))

        # No-show risk: long travel distance increases
        no_show_risk = 0.05 + (distance / 60) * 0.4 + np.random.normal(0, 0.08)
        no_show_risk = min(1, max(0, no_show_risk))

        risk_scores.append({
            "patient_id": pid,
            "readmission_risk": round(readmission_risk, 4),
            "icu_risk": round(icu_risk, 4),
            "no_show_risk": round(no_show_risk, 4),
            "risk_last_updated": base_date.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return pd.DataFrame(risk_scores)


def main():
    print("Generating Patient Digital Twin dataset...")
    print("-" * 50)

    # 1. Patients
    print("1. Generating patients...")
    patients_df = generate_patients()
    patients_df.to_csv("patients.csv", index=False)
    print(f"   -> patients.csv ({len(patients_df)} rows)")

    # 2. Admissions
    print("2. Generating admissions...")
    admissions_df = generate_admissions(patients_df)
    admissions_df.to_csv("admissions.csv", index=False)
    print(f"   -> admissions.csv ({len(admissions_df)} rows)")

    # 3. Vitals
    print("3. Generating vitals...")
    vitals_df = generate_vitals(patients_df, admissions_df)
    vitals_df.to_csv("vitals.csv", index=False)
    print(f"   -> vitals.csv ({len(vitals_df)} rows)")

    # 4. Appointments
    print("4. Generating appointments...")
    appointments_df = generate_appointments(patients_df)
    appointments_df.to_csv("appointments.csv", index=False)
    print(f"   -> appointments.csv ({len(appointments_df)} rows)")

    # 5. ICU beds
    print("5. Generating ICU beds...")
    icu_beds_df = generate_icu_beds(admissions_df, patients_df)
    icu_beds_df.to_csv("icu_beds.csv", index=False)
    print(f"   -> icu_beds.csv ({len(icu_beds_df)} rows)")

    # 6. Risk scores
    print("6. Generating risk scores...")
    risk_scores_df = generate_risk_scores(patients_df, appointments_df)
    risk_scores_df.to_csv("risk_scores.csv", index=False)
    print(f"   -> risk_scores.csv ({len(risk_scores_df)} rows)")

    # Summary statistics
    print("\n" + "=" * 50)
    print("SUMMARY STATISTICS")
    print("=" * 50)

    total_patients = len(patients_df)
    avg_age = patients_df["age"].mean()
    icu_occupied = icu_beds_df["occupied"].sum()
    icu_occupancy_rate = icu_occupied / N_ICU_BEDS * 100
    high_readmission = (risk_scores_df["readmission_risk"] > 0.6).sum()

    # Expected no-shows tomorrow: use appointments on busiest day and no_show_risk
    max_date = appointments_df["appointment_date"].max()
    tomorrow_appts = appointments_df[appointments_df["appointment_date"] == max_date]
    risk_lookup = dict(zip(risk_scores_df["patient_id"], risk_scores_df["no_show_risk"]))
    if len(tomorrow_appts) > 0:
        expected_noshow = sum(risk_lookup.get(pid, 0.1) for pid in tomorrow_appts["patient_id"])
        expected_noshow = round(expected_noshow, 1)
    else:
        avg_daily = N_APPOINTMENTS / 365
        expected_noshow = round(avg_daily * risk_scores_df["no_show_risk"].mean(), 1)

    print(f"   Total patients:              {total_patients:,}")
    print(f"   Average age:                 {avg_age:.1f} years")
    print(f"   ICU occupancy rate:          {icu_occupancy_rate:.1f}% ({icu_occupied}/{N_ICU_BEDS} beds)")
    print(f"   High readmission risk (>0.6): {high_readmission:,} patients")
    print(f"   Expected no-shows tomorrow:  {expected_noshow:.1f}")

    print("\nDone! All CSV files exported successfully.")


if __name__ == "__main__":
    main()
