# Hospital Operations Command Center

Streamlit-based decision support dashboard for hospital operations. Uses Supabase for data and optional LLM for recommendations and insights.

## Quick start

```bash
cd hospital_dashboard
pip install -r requirements.txt
# Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env (see hospital_dashboard/.env.example)
streamlit run streamlit_dashboard.py
```

See **hospital_dashboard/README.md** for full setup and structure.

## Repo layout

- **hospital_dashboard/** – Streamlit app and all backend (analytics, DB, LLM, forecasting).
- **Dataset for Hackathon/** – Sample CSVs and scripts to load data into Supabase (optional).
- **supabase_schema.sql** – Reference schema for Supabase tables.

## License

See LICENSE.
