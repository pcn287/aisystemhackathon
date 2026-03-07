#!/usr/bin/env bash
# Run the Streamlit hospital dashboard (use project venv if present)
cd "$(dirname "$0")"
if [ -d ".venv" ]; then
  exec .venv/bin/streamlit run streamlit_dashboard.py "$@"
else
  exec streamlit run streamlit_dashboard.py "$@"
fi
