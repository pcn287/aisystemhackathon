#!/usr/bin/env bash
# Run the hospital dashboard using the project's .venv (no need to activate manually)
cd "$(dirname "$0")"
exec .venv/bin/python -m shiny run app.py "$@"
