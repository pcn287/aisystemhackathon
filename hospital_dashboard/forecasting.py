"""
Decision support — simple ICU demand forecasting.

predict_icu_load(current_rate, historical_data) returns projections for 12h, 24h, 48h.
Uses linear projection or rolling average; no external ML.
"""

from typing import Any

import pandas as pd


def predict_icu_load(
    current_rate: float,
    historical_data: pd.DataFrame | None = None,
    icu_total_beds: int = 50,
) -> dict[str, float]:
    """
    Project ICU occupancy for next 12h, 24h, 48h.

    current_rate: 0–100 occupancy % (or 0–1; we normalize to 0–100).
    historical_data: optional DataFrame with "date" and "value" (daily occupancy or pressure).
    icu_total_beds: used only if we derive absolute bed count from rate.

    Uses simple linear trend from last 5 days of historical_data if available;
    otherwise returns current_rate with small drift.
    """
    if current_rate <= 1 and current_rate >= 0:
        current_rate = current_rate * 100.0
    current_rate = max(0, min(100, float(current_rate)))

    out = {"next_12h": current_rate, "next_24h": current_rate, "next_48h": current_rate}

    if historical_data is not None and not historical_data.empty and "value" in historical_data.columns and len(historical_data) >= 2:
        series = historical_data["value"].astype(float)
        # Rolling average of last 5 points
        window = min(5, len(series))
        recent = series.tail(window)
        avg = recent.mean()
        # Simple linear slope (last - first) / (n-1) per day -> per 12h = /2, per 24h = *1, per 48h = *2
        if len(recent) >= 2:
            slope_per_day = (recent.iloc[-1] - recent.iloc[0]) / max(1, len(recent) - 1)
            out["next_12h"] = round(min(100, max(0, current_rate + slope_per_day * 0.5)), 1)
            out["next_24h"] = round(min(100, max(0, current_rate + slope_per_day * 1)), 1)
            out["next_48h"] = round(min(100, max(0, current_rate + slope_per_day * 2)), 1)
        else:
            out["next_12h"] = round(min(100, max(0, (current_rate + avg) / 2)), 1)
            out["next_24h"] = round(min(100, max(0, avg)), 1)
            out["next_48h"] = round(min(100, max(0, avg)), 1)
    else:
        # No history: hold current with tiny random drift for demo (deterministic)
        out["next_12h"] = current_rate
        out["next_24h"] = round(min(100, max(0, current_rate + 1)), 1)
        out["next_48h"] = round(min(100, max(0, current_rate + 2)), 1)

    return out
