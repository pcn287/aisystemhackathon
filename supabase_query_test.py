"""
Supabase database query test script.

Verifies connectivity and prints sample rows from each main table used by
the hospital analytics and dashboards. Run this to confirm the Supabase
connection and table contents before starting the dashboard.

Usage:
    python supabase_query_test.py

Run from project root or from hospital_dashboard (where .env usually lives).
Requires: python-dotenv, supabase
    pip install python-dotenv supabase

Environment variables (in .env or shell):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root or hospital_dashboard
_root = Path(__file__).resolve().parent
_env_paths = [
    _root / ".env",
    _root / "hospital_dashboard" / ".env",
    Path.cwd() / ".env",
]
for p in _env_paths:
    if p.exists():
        load_dotenv(p)
        break
load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print("ERROR: Missing Supabase credentials.")
    print("  Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env or environment.")
    if not url:
        print("  SUPABASE_URL is missing.")
    if not key:
        print("  SUPABASE_SERVICE_ROLE_KEY is missing.")
    exit(1)

from supabase import create_client

supabase = create_client(url, key)

TABLES = [
    "patients",
    "admissions",
    "appointments",
    "risk_scores",
    "icu_beds",
    "vitals",
]

def main():
    print("Supabase connection test")
    print("=" * 50)
    print(f"URL: {url[:50]}...")
    print()

    for table in TABLES:
        try:
            response = supabase.table(table).select("*").limit(5).execute()
            rows = response.data or []
            print(f"\nTable: {table}")
            print(f"Rows returned: {len(rows)}")
            if rows:
                for i, row in enumerate(rows[:2]):
                    print(f"  Example row {i + 1}: {row}")
            else:
                print("  (no rows)")
        except Exception as e:
            print(f"\nTable: {table}")
            print(f"Error: {e}")

    print("\n" + "=" * 50)
    print("Done.")

if __name__ == "__main__":
    main()
