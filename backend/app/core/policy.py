"""Configuration inheritance engine.

A configuration value can be defined at several scopes. The MOST SPECIFIC valid
rule wins:

    company (1) -> branch (2) -> division (3) -> project (4) -> employee (5)

Nothing is hard-coded: policy definitions and their values live in the database
(`config_overrides`), so each tenant can shape its own rules.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from .db import NO_ID, get_db

SCOPE_PRECEDENCE = {
    "company": 1,
    "branch": 2,
    "division": 3,
    "project": 4,
    "employee": 5,
}

SCOPE_LABELS = {
    "company": "Perusahaan (Default)",
    "branch": "Cabang",
    "division": "Divisi",
    "project": "Proyek",
    "employee": "Karyawan",
}

# Policy catalogue. Business calculations are intentionally NOT implemented in this
# phase - only the configurable definition + inheritance resolution.
POLICY_GROUPS: List[Dict[str, Any]] = [
    {
        "key": "attendance",
        "name": "Kebijakan Absensi",
        "module": "attendance",
        "policies": [
            {"key": "attendance.work_days_per_week", "name": "Hari Kerja per Minggu", "type": "number", "default": 5, "unit": "hari"},
            {"key": "attendance.work_hours_per_day", "name": "Jam Kerja per Hari", "type": "number", "default": 8, "unit": "jam"},
            {"key": "attendance.late_tolerance_minutes", "name": "Toleransi Keterlambatan", "type": "number", "default": 10, "unit": "menit"},
            {"key": "attendance.require_geofence", "name": "Wajib Geofence", "type": "boolean", "default": False},
        ],
    },
    {
        "key": "leave",
        "name": "Kebijakan Cuti",
        "module": "leave_overtime",
        "policies": [
            {"key": "leave.annual_quota_days", "name": "Kuota Cuti Tahunan", "type": "number", "default": 12, "unit": "hari"},
            {"key": "leave.max_carry_over_days", "name": "Maksimal Cuti Dibawa", "type": "number", "default": 6, "unit": "hari"},
            {"key": "leave.min_notice_days", "name": "Minimal Pengajuan Sebelum", "type": "number", "default": 3, "unit": "hari"},
        ],
    },
    {
        "key": "overtime",
        "name": "Kebijakan Lembur",
        "module": "leave_overtime",
        "policies": [
            {"key": "overtime.requires_preapproval", "name": "Wajib Disetujui Sebelum Lembur", "type": "boolean", "default": True},
            {"key": "overtime.max_hours_per_month", "name": "Maksimal Jam Lembur per Bulan", "type": "number", "default": 40, "unit": "jam"},
        ],
    },
    {
        "key": "payroll",
        "name": "Kebijakan Payroll",
        "module": "payroll",
        "policies": [
            {"key": "payroll.cut_off_day", "name": "Tanggal Cut-Off", "type": "number", "default": 25, "unit": "tanggal"},
            {"key": "payroll.payment_day", "name": "Tanggal Pembayaran", "type": "number", "default": 28, "unit": "tanggal"},
            {"key": "payroll.currency", "name": "Mata Uang", "type": "text", "default": "IDR"},
        ],
    },
    {
        "key": "contract",
        "name": "Kebijakan Kontrak",
        "module": "employee_core",
        "policies": [
            {"key": "contract.expiry_reminder_days", "name": "Peringatan Sebelum Kontrak Berakhir", "type": "number", "default": 30, "unit": "hari"},
            {"key": "contract.probation_months", "name": "Masa Percobaan", "type": "number", "default": 3, "unit": "bulan"},
        ],
    },
    {
        "key": "approval",
        "name": "Kebijakan Persetujuan",
        "module": "hr_core",
        "policies": [
            {"key": "approval.allow_delegation", "name": "Izinkan Delegasi Persetujuan", "type": "boolean", "default": True},
            {"key": "approval.auto_escalate_days", "name": "Eskalasi Otomatis Setelah", "type": "number", "default": 3, "unit": "hari"},
        ],
    },
]

POLICY_INDEX: Dict[str, Dict[str, Any]] = {}
for _g in POLICY_GROUPS:
    for _p in _g["policies"]:
        POLICY_INDEX[_p["key"]] = {**_p, "group": _g["key"], "group_name": _g["name"], "module": _g["module"]}


def _active(row: Dict[str, Any], at: Optional[datetime] = None) -> bool:
    at = at or datetime.now(timezone.utc)
    if row.get("status") not in (None, "active"):
        return False

    def _norm(v):
        if v in (None, ""):
            return None
        if isinstance(v, datetime):
            return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
        if isinstance(v, date):
            return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(v))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except Exception:
            return None

    ef, et = _norm(row.get("effective_from")), _norm(row.get("effective_to"))
    if ef and at < ef:
        return False
    if et and at > et:
        return False
    return True


async def resolve_config(
    company_id: str,
    config_key: str,
    context: Optional[Dict[str, Optional[str]]] = None,
    at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return {value, scope_type, scope_id, source} choosing the most specific rule."""
    context = context or {}
    db = get_db()
    rows = await db.config_overrides.find(
        {"company_id": company_id, "config_key": config_key}, NO_ID
    ).to_list(500)

    scope_ids = {
        "company": company_id,
        "branch": context.get("branch_id"),
        "division": context.get("division_id"),
        "project": context.get("project_id"),
        "employee": context.get("employee_id"),
    }

    best, best_rank = None, 0
    for row in rows:
        scope = row.get("scope_type")
        if scope not in SCOPE_PRECEDENCE:
            continue
        expected = scope_ids.get(scope)
        if scope != "company" and (expected is None or row.get("scope_id") != expected):
            continue
        if not _active(row, at):
            continue
        rank = SCOPE_PRECEDENCE[scope]
        if rank > best_rank:
            best, best_rank = row, rank

    definition = POLICY_INDEX.get(config_key, {})
    if best is None:
        return {
            "config_key": config_key,
            "value": definition.get("default"),
            "scope_type": "system_default",
            "scope_id": None,
            "source": "Nilai bawaan sistem",
            "override_id": None,
        }
    return {
        "config_key": config_key,
        "value": best.get("value"),
        "scope_type": best["scope_type"],
        "scope_id": best.get("scope_id"),
        "source": SCOPE_LABELS.get(best["scope_type"], best["scope_type"]),
        "override_id": best.get("id"),
    }


async def resolve_many(
    company_id: str, keys: List[str], context: Optional[Dict[str, Optional[str]]] = None
) -> Dict[str, Any]:
    return {k: await resolve_config(company_id, k, context) for k in keys}
