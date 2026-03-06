-- Run this in Supabase SQL Editor (Dashboard > SQL Editor) before importing CSV data
-- Creates tables for the Hackathon dataset

-- Patients table (parent - referenced by others)
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    age INTEGER,
    gender TEXT,
    zip_code TEXT,
    insurance_type TEXT,
    smoking_status BOOLEAN,
    bmi NUMERIC,
    chronic_conditions TEXT,
    primary_diagnosis TEXT
);

-- Admissions
CREATE TABLE IF NOT EXISTS admissions (
    admission_id TEXT PRIMARY KEY,
    patient_id TEXT REFERENCES patients(patient_id),
    admission_date DATE,
    discharge_date DATE,
    diagnosis_code TEXT,
    admission_type TEXT,
    icu_required BOOLEAN,
    length_of_stay INTEGER,
    previous_admissions INTEGER
);

-- Appointments
CREATE TABLE IF NOT EXISTS appointments (
    appointment_id TEXT PRIMARY KEY,
    patient_id TEXT REFERENCES patients(patient_id),
    appointment_date DATE,
    department TEXT,
    appointment_time TIME,
    reminder_sent BOOLEAN,
    distance_to_hospital INTEGER,
    no_show BOOLEAN
);

-- ICU Beds
CREATE TABLE IF NOT EXISTS icu_beds (
    bed_id TEXT PRIMARY KEY,
    ward TEXT,
    occupied BOOLEAN,
    patient_id TEXT REFERENCES patients(patient_id),
    expected_discharge_date DATE
);

-- Risk Scores
CREATE TABLE IF NOT EXISTS risk_scores (
    patient_id TEXT PRIMARY KEY REFERENCES patients(patient_id),
    readmission_risk NUMERIC,
    icu_risk NUMERIC,
    no_show_risk NUMERIC,
    risk_last_updated TIMESTAMP
);

-- Vitals
CREATE TABLE IF NOT EXISTS vitals (
    record_id BIGINT PRIMARY KEY,
    patient_id TEXT REFERENCES patients(patient_id),
    timestamp TIMESTAMP,
    heart_rate INTEGER,
    systolic_bp INTEGER,
    respiratory_rate INTEGER,
    oxygen_saturation INTEGER,
    temperature NUMERIC
);

-- Create indexes for common queries (useful for MCP)
CREATE INDEX IF NOT EXISTS idx_admissions_patient ON admissions(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_vitals_patient ON vitals(patient_id);

-- Enable Row Level Security (RLS) - optional: disable for simpler MCP access
-- ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
-- For development, you may want to allow all operations. Run this if needed:
-- CREATE POLICY "Allow all" ON patients FOR ALL USING (true) WITH CHECK (true);
-- (Repeat for other tables, or disable RLS: ALTER TABLE patients DISABLE ROW LEVEL SECURITY;)
