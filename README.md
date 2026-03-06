# AI System Hackathon

Hackathon project: **Patient Digital Twin Hospital Intelligence Dashboard**.

## Contents

| Folder | Description |
|--------|-------------|
| **hospital_dashboard/** | Shiny for Python dashboard — Supabase data, analytics, risk models, LLM insights |
| **Dataset for Hackathon/** | Synthetic hospital CSVs and dataset generator |

## Quick start (dashboard)

```bash
cd hospital_dashboard
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Set SUPABASE_URL, SUPABASE_KEY (see .env.example)
shiny run app.py
```

See [hospital_dashboard/README.md](hospital_dashboard/README.md) for full setup and hospital assumptions.
