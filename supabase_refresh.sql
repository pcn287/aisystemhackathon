-- Run this in Supabase SQL Editor (Dashboard > SQL Editor) to CLEAR all data
-- before re-importing your updated CSV dataset.
--
-- Order: child tables first (vitals, risk_scores, icu_beds, appointments, admissions), then patients.

TRUNCATE vitals, risk_scores, icu_beds, appointments, admissions, patients RESTART IDENTITY CASCADE;
