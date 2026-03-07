"""
Column name and schema constants. Use these everywhere so a single change
updates all layers. All risk scores must be float 0.0-1.0 by the time they reach app.py.
"""
PATIENT_ID_COL = "patient_id"
READMISSION_RISK_COL = "readmission_risk"
APPOINTMENT_DATE_COL = "appointment_date"
DEPARTMENT_COL = "department"
NO_SHOW_COL = "no_show"
ADMISSION_DATE_COL = "admission_date"
DISCHARGE_DATE_COL = "discharge_date"
NO_SHOW_RATE_COL = "no_show_rate"
EXPECTED_DISCHARGE_DATE_COL = "expected_discharge_date"

# Empty DataFrame column contracts (for consistent empty returns)
HIGH_RISK_EMPTY_COLS = [PATIENT_ID_COL, READMISSION_RISK_COL, "admission_count"]
DEPT_NO_SHOW_EMPTY_COLS = [DEPARTMENT_COL, "total_appointments", "no_shows", NO_SHOW_RATE_COL]
TREND_EMPTY_COLS = ["date", "admissions", "discharges"]
