@echo off
REM Run the Streamlit hospital dashboard (use project venv if present)
cd /d "%~dp0"
if exist ".venv\Scripts\streamlit.exe" (
  .venv\Scripts\streamlit.exe run streamlit_dashboard.py %*
) else (
  streamlit run streamlit_dashboard.py %*
)
