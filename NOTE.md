# Project Notes

## risk_models.py

`risk_models.py` defines heuristic risk calculators (readmission, ICU, no-show) but is **not used** anywhere in the app. The dashboard uses pre-computed risk scores from `risk_scores.csv` (imported to Supabase) instead. This module is effectively dead code—kept as a fallback or reference for on-the-fly risk calculation.
