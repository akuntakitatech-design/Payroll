"""Shared helpers for masa berlaku (expiry) handling across contracts, certifications
and documents. Kept in one place so every module uses the same rules & wording.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

STATE_LABELS = {
    "expired": "Kedaluwarsa",
    "due_soon": "Segera berakhir",
    "ok": "Masih berlaku",
    "none": "Tanpa masa berlaku",
}

MONTH_NAMES_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value)[:19])
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def days_left(value: Any, today: Optional[datetime] = None) -> Optional[int]:
    parsed = parse_date(value)
    if not parsed:
        return None
    base = today or datetime.now(timezone.utc)
    return (parsed.date() - base.date()).days


def expiry_state(value: Any, horizon_days: int = 30, today: Optional[datetime] = None) -> Dict[str, Any]:
    """Returns {expiry_date, days_left, state, state_label}."""
    left = days_left(value, today)
    if left is None:
        state = "none"
    elif left < 0:
        state = "expired"
    elif left <= horizon_days:
        state = "due_soon"
    else:
        state = "ok"
    return {
        "expiry_date": value,
        "days_left": left,
        "state": state,
        "state_label": STATE_LABELS[state],
    }


def month_key(value: Any) -> Optional[str]:
    parsed = parse_date(value)
    if not parsed:
        return None
    return f"{parsed.year:04d}-{parsed.month:02d}"


def month_label(key: str) -> str:
    try:
        year, month = key.split("-")
        return f"{MONTH_NAMES_ID[int(month) - 1]} {year}"
    except Exception:  # noqa: BLE001
        return key
