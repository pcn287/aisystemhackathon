# Hospital Operations Command Center (Streamlit)

Streamlit dashboard for hospital operations: ICU capacity, readmission risk, no-show risk, trends, forecasting, and LLM-powered recommendations. Data from Supabase (PostgreSQL).

## Structure

```
hospital_dashboard/
├── streamlit_dashboard.py   # Main app (run this)
├── hospital_analytics.py    # Analytics: strain, readmission, no-show, trends
├── hospital_ai_agent.py     # LLM: answers, recommendations, situation brief
├── database_connection.py   # Supabase REST client
├── data_queries.py          # Trend data for charts
├── analytics.py             # Root-cause analysis, strain score
├── forecasting.py           # ICU demand projection
├── llm_insights.py          # Re-exports LLM helpers
├── constants.py             # Schema/column constants
├── dashboard_log.py         # Logging
├── requirements.txt
├── .env.example
├── run.sh / run.bat         # Run scripts
└── README.md
```

## Setup

1. **Virtual environment** (from this directory):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Environment**: Copy `.env.example` to `.env` and set:

   - `SUPABASE_URL` – Supabase project URL  
   - `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_KEY`  
   - Optional: `OPENAI_API_KEY` or `LLM_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`

3. **Run**:

   ```bash
   streamlit run streamlit_dashboard.py
   ```

   Or use `./run.sh` / `run.bat` if you use `.venv` here.

## Tabs

- **Command Center** – KPIs, strain score, ICU gauge, bed grid, AI situation brief, recommendations, ICU forecast  
- **ICU Capacity** – Gauge, bed grid, admissions/discharges trend  
- **Readmission Risk** – High-risk patients, filters, root-cause drivers  
- **No-Show Risk** – Department rates, at-risk appointments  
- **Patient Twin** – Select patient, load twin, vitals, AI insight  
- **Trends** – ICU / readmission / no-show trends, admissions chart  
- **AI Assistant** – Natural-language questions
