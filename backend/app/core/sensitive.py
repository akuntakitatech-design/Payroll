"""Upgrade 01C - masking data sensitif karyawan (server-side).

Aturan 01C (tanpa permission baru):
- user dengan `employee:edit` -> nilai penuh;
- user yang hanya `employee:view` -> nilai dimasking di API (bukan hanya di frontend).
Audit log SELALU menyimpan versi masking (tidak pernah nilai penuh).
"""
from typing import Any, Dict, Iterable, List, Optional

# Field karyawan yang dimasking untuk user view-only.
# 01C carry-over: NIK KTP (`nik`) ikut disamarkan untuk user view-only.
EMPLOYEE_SENSITIVE_FIELDS = ("nik", "bank_account_number", "npwp", "bpjs_kesehatan_number", "bpjs_tk_number")
# Field yang dimasking di audit log (nilai penuh tidak pernah disimpan di audit).
AUDIT_MASKED_FIELDS = set(EMPLOYEE_SENSITIVE_FIELDS)


def mask_value(value: Any, keep: int = 4) -> Any:
    """'1234567890' -> '******7890'. Nilai kosong dikembalikan apa adanya."""
    if value is None or value == "":
        return value
    text = str(value)
    if len(text) <= keep:
        return "*" * len(text)
    return "*" * (len(text) - keep) + text[-keep:]


def can_view_sensitive(ctx) -> bool:
    return bool(ctx and ctx.has_permission("employee", "edit"))


def mask_employee(doc: Optional[Dict[str, Any]], fields: Iterable[str] = EMPLOYEE_SENSITIVE_FIELDS) -> Optional[Dict[str, Any]]:
    if not doc:
        return doc
    out = dict(doc)
    for f in fields:
        if out.get(f):
            out[f] = mask_value(out[f])
    out["sensitive_masked"] = True
    return out


def apply_employee_masking(ctx, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Masking daftar karyawan bila user tidak punya employee:edit."""
    if can_view_sensitive(ctx):
        return items
    return [mask_employee(i) for i in items]


def _mask_deep(value: Any, depth: int = 0) -> Any:
    """Masking rekursif (dict/list bersarang, mis. item payroll di before/after audit)."""
    if depth > 6:
        return value
    if isinstance(value, dict):
        return {k: (mask_value(v) if k in AUDIT_MASKED_FIELDS and v and not isinstance(v, (dict, list))
                    else _mask_deep(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_deep(v, depth + 1) for v in value]
    return value


def mask_for_audit(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    return _mask_deep(data)
