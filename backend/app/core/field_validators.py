"""Validator format field karyawan yang dipakai bersama (Upgrade 01F).

Aturan digit/enum DIAMBIL dari mapping impor 01E (`employee_import_mapping`) sehingga hanya ada satu
sumber kebenaran. Modul ini TIDAK dipakai untuk menolak penyimpanan existing (perilaku simpan 01C/01E
tidak berubah); 01F memakainya untuk menandai status INVALID pada hasil kelengkapan.
"""
import re
from datetime import date
from typing import Any, Optional

from .employee_import_mapping import DIGIT_RULES, ENUMS

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def digits_ok(kind: str, value: Any) -> bool:
    lo, hi = DIGIT_RULES[kind]
    raw = re.sub(r"[\s.\-]", "", str(value or ""))
    return raw.isdigit() and lo <= len(raw) <= hi


def date_ok(value: Any, allow_future: bool = False) -> bool:
    try:
        d = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return False
    return allow_future or d <= date.today()


def phone_ok(value: Any) -> bool:
    raw = re.sub(r"[\s()\-]", "", str(value or ""))
    if raw.startswith("+"):
        raw = raw[1:]
    return raw.isdigit() and 8 <= len(raw) <= 15


def email_ok(value: Any) -> bool:
    return bool(_EMAIL.match(str(value or "").strip()))


def enum_ok(kind: str, value: Any) -> bool:
    allowed = set(ENUMS.get(kind, {}).values())
    return not allowed or str(value).strip().lower() in {a.lower() for a in allowed}


def check(validator: Optional[str], value: Any) -> bool:
    """True bila nilai (yang sudah tidak kosong) valid menurut validator key."""
    if not validator:
        return True
    if validator in DIGIT_RULES:
        return digits_ok(validator, value)
    if validator == "date":
        return date_ok(value)
    if validator == "phone":
        return phone_ok(value)
    if validator == "email":
        return email_ok(value)
    if validator.startswith("enum:"):
        return enum_ok(validator[5:], value)
    if validator == "min2":
        return len(str(value).strip()) >= 2
    return True
