"""
Decision support — LLM-powered insights (re-exports and thin wrappers).

Operational recommendations, situation brief, and patient digital twin insight
are implemented in hospital_ai_agent; this module provides a single import surface
for the dashboard.
"""

from hospital_ai_agent import (
    generate_operational_recommendations,
    generate_situation_brief,
    patient_digital_twin_insight,
)

__all__ = [
    "generate_operational_recommendations",
    "generate_situation_brief",
    "patient_digital_twin_insight",
]
