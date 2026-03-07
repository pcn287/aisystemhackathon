# Project Notes

## 30-Day Readmission in US Hospitals & Insurance

**Why it matters:** 30-day readmissions are tied to Medicare penalties (HRRP), used as quality-of-care indicators, and cost ~$17,700 per readmission (~$60B/year in the US). High rates suggest poor discharge planning or care coordination.

**Key drivers:** CMS reduces payments for "excess" readmissions. Value-based care rewards better outcomes over volume. High readmission rates hurt hospital reputation and patient safety.

**Our aim:** Use data to identify high-risk patients and support targeted interventions (discharge planning, follow-up, care coordination) to reduce preventable readmissions.

---

## risk_models.py

`risk_models.py` defines heuristic risk calculators (readmission, ICU, no-show) but is **not used** anywhere in the app. The dashboard uses pre-computed risk scores from `risk_scores.csv` (imported to Supabase) instead. This module is effectively dead code—kept as a fallback or reference for on-the-fly risk calculation.
