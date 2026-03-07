"""
Structured logging for the dashboard. When DEBUG=1 (or DEBUG=true/yes), logs to stdout.
Errors are always logged when passed to log_error().
"""
import os

DEBUG = os.environ.get("DEBUG", "").strip().lower() in ("1", "true", "yes")


def log(stage: str, message: str, **kwargs) -> None:
    """Log when DEBUG is enabled. kwargs are printed as key=value."""
    if not DEBUG:
        return
    parts = [f"[{stage}] {message}"]
    for k, v in kwargs.items():
        parts.append(f" {k}={v}")
    print("".join(parts))


def log_error(stage: str, message: str, error: BaseException | None = None) -> None:
    """Always log errors so they are visible even without DEBUG."""
    line = f"[{stage}] ERROR: {message}"
    if error is not None:
        line += f" — {type(error).__name__}: {error}"
    print(line)


def log_empty(stage: str, query_or_step: str, row_count: int = 0) -> None:
    """Log when data is empty (diagnostic)."""
    if DEBUG:
        print(f"[{stage}] {query_or_step} returned: {row_count} rows")
    elif row_count == 0:
        print(f"[{stage}] (empty) {query_or_step} — set DEBUG=1 for full pipeline logs")
