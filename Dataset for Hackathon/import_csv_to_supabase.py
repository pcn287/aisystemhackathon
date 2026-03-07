"""
Import CSV data from Dataset for Hackathon into Supabase.
Run supabase_schema.sql in Supabase SQL Editor first, then run this script.

Uses Supabase REST API directly (no supabase package - avoids build issues on Windows).

Usage:
    python import_csv_to_supabase.py

To REFRESH after changing the dataset:
    1. Put your updated CSVs in this folder (Dataset for Hackathon)
    2. Run supabase_refresh.sql in Supabase Dashboard > SQL Editor (clears all data)
    3. Run: python import_csv_to_supabase.py
"""

import os
import csv
from pathlib import Path
from dotenv import load_dotenv
import requests

# Load environment variables (script is inside Dataset for Hackathon folder)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
DATASET_DIR = Path(__file__).parent  # CSVs are in same folder as this script
BATCH_SIZE = 500  # Insert in batches to avoid timeouts


def get_headers() -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env\n"
            "Get these from Supabase Dashboard > Project Settings > API\n"
            "Use the service_role key (bypasses RLS)"
        )
    return {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def insert_batch(table: str, rows: list) -> None:
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
    resp = requests.post(url, headers=get_headers(), json=rows)
    resp.raise_for_status()


def parse_bool(val: str):
    if val is None or val == "":
        return None
    return str(val).lower() in ("true", "1", "yes")


def import_patients() -> None:
    path = DATASET_DIR / "patients.csv"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            rows.append({
                "patient_id": r["patient_id"],
                "age": int(r["age"]) if r["age"] else None,
                "gender": r["gender"] or None,
                "zip_code": r["zip_code"] or None,
                "insurance_type": r["insurance_type"] or None,
                "smoking_status": parse_bool(r["smoking_status"]),
                "bmi": float(r["bmi"]) if r["bmi"] else None,
                "chronic_conditions": r["chronic_conditions"] or None,
                "primary_diagnosis": r["primary_diagnosis"] or None,
            })
    for i in range(0, len(rows), BATCH_SIZE):
        insert_batch("patients", rows[i : i + BATCH_SIZE])
    print(f"  Imported {len(rows)} patients")


def import_admissions() -> None:
    path = DATASET_DIR / "admissions.csv"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            rows.append({
                "admission_id": r["admission_id"],
                "patient_id": r["patient_id"],
                "admission_date": r["admission_date"] or None,
                "discharge_date": r["discharge_date"] or None,
                "diagnosis_code": r["diagnosis_code"] or None,
                "admission_type": r["admission_type"] or None,
                "icu_required": parse_bool(r["icu_required"]),
                "length_of_stay": int(r["length_of_stay"]) if r["length_of_stay"] else None,
                "previous_admissions": int(r["previous_admissions"]) if r["previous_admissions"] else None,
            })
    for i in range(0, len(rows), BATCH_SIZE):
        insert_batch("admissions", rows[i : i + BATCH_SIZE])
    print(f"  Imported {len(rows)} admissions")


def import_appointments() -> None:
    path = DATASET_DIR / "appointments.csv"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            rows.append({
                "appointment_id": r["appointment_id"],
                "patient_id": r["patient_id"],
                "appointment_date": r["appointment_date"] or None,
                "department": r["department"] or None,
                "appointment_time": r["appointment_time"] or None,
                "reminder_sent": parse_bool(r["reminder_sent"]),
                "distance_to_hospital": int(r["distance_to_hospital"]) if r["distance_to_hospital"] else None,
                "no_show": parse_bool(r["no_show"]),
            })
    for i in range(0, len(rows), BATCH_SIZE):
        insert_batch("appointments", rows[i : i + BATCH_SIZE])
    print(f"  Imported {len(rows)} appointments")


def import_icu_beds() -> None:
    path = DATASET_DIR / "icu_beds.csv"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            rows.append({
                "bed_id": r["bed_id"],
                "ward": r["ward"] or None,
                "occupied": parse_bool(r["occupied"]),
                "patient_id": r["patient_id"] or None,
                "expected_discharge_date": r["expected_discharge_date"] or None,
            })
    for i in range(0, len(rows), BATCH_SIZE):
        insert_batch("icu_beds", rows[i : i + BATCH_SIZE])
    print(f"  Imported {len(rows)} icu_beds")


def import_risk_scores() -> None:
    path = DATASET_DIR / "risk_scores.csv"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            rows.append({
                "patient_id": r["patient_id"],
                "readmission_risk": float(r["readmission_risk"]) if r["readmission_risk"] else None,
                "icu_risk": float(r["icu_risk"]) if r["icu_risk"] else None,
                "no_show_risk": float(r["no_show_risk"]) if r["no_show_risk"] else None,
                "risk_last_updated": r["risk_last_updated"] or None,
            })
    for i in range(0, len(rows), BATCH_SIZE):
        insert_batch("risk_scores", rows[i : i + BATCH_SIZE])
    print(f"  Imported {len(rows)} risk_scores")


def import_vitals() -> None:
    path = DATASET_DIR / "vitals.csv"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            rows.append({
                "record_id": int(r["record_id"]),
                "patient_id": r["patient_id"],
                "timestamp": r["timestamp"] or None,
                "heart_rate": int(r["heart_rate"]) if r["heart_rate"] else None,
                "systolic_bp": int(r["systolic_bp"]) if r["systolic_bp"] else None,
                "respiratory_rate": int(r["respiratory_rate"]) if r["respiratory_rate"] else None,
                "oxygen_saturation": int(r["oxygen_saturation"]) if r["oxygen_saturation"] else None,
                "temperature": float(r["temperature"]) if r["temperature"] else None,
            })
    for i in range(0, len(rows), BATCH_SIZE):
        insert_batch("vitals", rows[i : i + BATCH_SIZE])
    print(f"  Imported {len(rows)} vitals")


def main() -> None:
    get_headers()  # Validate env vars

    if not DATASET_DIR.exists():
        raise SystemExit(f"Dataset folder not found: {DATASET_DIR}")

    print("Importing CSV data to Supabase (order matters for foreign keys)...")
    import_patients()
    import_admissions()
    import_appointments()
    import_icu_beds()
    import_risk_scores()
    import_vitals()

    print("\nDone! Data is now in your Supabase database.")


if __name__ == "__main__":
    main()
