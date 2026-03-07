#!/usr/bin/env python3
"""
Verify Supabase returns data for risk_scores and appointments.
Run from hospital_dashboard: python verify_supabase_data.py
Equivalent to: supabase.table("risk_scores").select("*").execute() and appointments.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv()

from database_connection import get_risk_scores, get_appointments

def main():
    print("=== Supabase data verification ===\n")

    print("1. risk_scores table")
    try:
        df = get_risk_scores()
        print(f"   Rows: {len(df)}")
        print(f"   Columns: {list(df.columns)}")
        if "readmission_risk" in df.columns:
            high = (df["readmission_risk"].astype(float) >= 0.6).sum()
            print(f"   Rows with readmission_risk >= 0.6: {high}")
        if not df.empty:
            print(f"   Sample: {df.head(1).to_dict('records')}")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n2. appointments table")
    try:
        df = get_appointments()
        print(f"   Rows: {len(df)}")
        print(f"   Columns: {list(df.columns)}")
        if "department" in df.columns:
            print(f"   Departments: {df['department'].dropna().unique().tolist()[:10]}")
        if "no_show" in df.columns:
            print(f"   No-shows (True count): {df['no_show'].fillna(False).astype(bool).sum()}")
        if not df.empty:
            print(f"   Sample: {df.head(1).to_dict('records')}")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n3. Analytics pipeline (high-risk patients)")
    try:
        from hospital_analytics import get_high_readmission_patients
        df = get_high_readmission_patients(limit=5)
        print(f"   Rows returned: {len(df)}")
        print(f"   Columns: {list(df.columns)}")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n4. Analytics pipeline (department no-show rates)")
    try:
        from hospital_analytics import get_department_no_show_rates
        df = get_department_no_show_rates()
        print(f"   Rows returned: {len(df)}")
        print(f"   Columns: {list(df.columns)}")
        if not df.empty:
            print(df.to_string())
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\nDone.")

if __name__ == "__main__":
    main()
