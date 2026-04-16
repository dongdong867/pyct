"""Datetime classification benchmark target.

Category: Date parsing with multi-format detection and temporal reasoning
Intent: Parse a date string across ISO, US, and EU formats then classify by day type,
    business hours, fiscal quarter, temporal relation, and holiday proximity.
Challenge: Multiple strptime format attempts combined with calendar-based branching
    (weekend, quarter, holiday proximity) create paths that depend on specific
    numeric properties of the parsed date, not just string structure.
"""

from __future__ import annotations

from datetime import datetime

_BUSINESS_HOUR_START = 9
_BUSINESS_HOUR_END = 17

_REFERENCE_DATE = datetime(2026, 1, 1)

_US_HOLIDAYS_MONTH_DAY = frozenset(
    {
        (1, 1),  # New Year's Day
        (7, 4),  # Independence Day
        (12, 25),  # Christmas Day
    }
)


def _try_iso_format(date_str: str) -> datetime | None:
    """Try parsing ISO datetime formats (with and without time)."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _try_us_format(date_str: str) -> datetime | None:
    """Try parsing US date format (MM/DD/YYYY)."""
    try:
        return datetime.strptime(date_str, "%m/%d/%Y")
    except ValueError:
        return None


def _try_eu_format(date_str: str) -> datetime | None:
    """Try parsing EU date format (DD.MM.YYYY)."""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        return None


def _classify_day_type(dt: datetime) -> str:
    """Classify weekday vs weekend."""
    if dt.weekday() >= 5:
        return "weekend"
    return "weekday"


def _classify_business_hours(dt: datetime) -> str:
    """Classify whether the time falls within business hours."""
    if _BUSINESS_HOUR_START <= dt.hour < _BUSINESS_HOUR_END:
        return "business_hours"
    return "after_hours"


def _classify_quarter(dt: datetime) -> str:
    """Return fiscal quarter label (calendar-year quarters)."""
    quarter = (dt.month - 1) // 3 + 1
    return f"Q{quarter}"


def _classify_temporal_relation(dt: datetime) -> str:
    """Classify whether the date is in the past or future relative to reference."""
    if dt < _REFERENCE_DATE:
        return "past"
    return "future"


def _classify_holiday_proximity(dt: datetime) -> str:
    """Check if the date is a known holiday, near one, or regular."""
    key = (dt.month, dt.day)
    if key in _US_HOLIDAYS_MONTH_DAY:
        return "holiday"
    for h_month, h_day in _US_HOLIDAYS_MONTH_DAY:
        if dt.month == h_month and abs(dt.day - h_day) <= 1:
            return "near_holiday"
    return "regular"


def datetime_classification(date_str: str) -> str:
    """Parse a date string and return a multi-facet classification."""
    if len(date_str) == 0:
        return "invalid_empty"

    stripped = date_str.strip()

    dt = _try_iso_format(stripped)
    if dt is not None:
        fmt_name = "iso"
    else:
        dt = _try_us_format(stripped)
        if dt is not None:
            fmt_name = "us"
        else:
            dt = _try_eu_format(stripped)
            if dt is not None:
                fmt_name = "eu"
            else:
                return "invalid_format"

    day_type = _classify_day_type(dt)
    hours = _classify_business_hours(dt)
    quarter = _classify_quarter(dt)
    temporal = _classify_temporal_relation(dt)
    holiday = _classify_holiday_proximity(dt)

    return f"{fmt_name}|{day_type}|{hours}|{quarter}|{temporal}|{holiday}"
