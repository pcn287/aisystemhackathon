@echo off
REM Run the hospital dashboard using the project's .venv (no need to activate manually)
cd /d "%~dp0"
.venv\Scripts\python.exe -m shiny run app.py %*
