"""Central audit trail. Records who changed what, when, and the before/after values."""
from typing import Any, Dict, List, Optional

from .db import NO_ID, get_db, new_id, now
from .rbac import resource_module
from .sensitive import mask_for_audit

SENSITIVE_KEYS = {"password_hash", "password", "refresh_token"}


def _sanitize(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    return {k: v for k, v in data.items() if k not in SENSITIVE_KEYS and k != "_id"}


def _stored(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Nilai yang DISIMPAN di audit: tanpa rahasia + data sensitif karyawan dimasking (01C)."""
    return mask_for_audit(_sanitize(data))


def diff(before: Optional[Dict], after: Optional[Dict]) -> List[str]:
    b, a = _sanitize(before) or {}, _sanitize(after) or {}
    changed = []
    for key in set(b) | set(a):
        if key in ("updated_at", "updated_by", "created_at", "created_by"):
            continue
        if b.get(key) != a.get(key):
            changed.append(key)
    return sorted(changed)


async def log_action(
    ctx,
    action: str,
    resource: str,
    record_id: Optional[str] = None,
    record_label: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    module: Optional[str] = None,
    company_id: Optional[str] = None,
    notes: Optional[str] = None,
    platform_scope: bool = False,
) -> Dict[str, Any]:
    entry = build_audit_entry(ctx, action, resource, record_id, record_label, before, after,
                              module, company_id, notes, platform_scope)
    await get_db().audit_logs.insert_one(dict(entry))
    return {k: v for k, v in entry.items() if k != "_id"}


def build_audit_entry(
    ctx,
    action: str,
    resource: str,
    record_id: Optional[str] = None,
    record_label: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    module: Optional[str] = None,
    company_id: Optional[str] = None,
    notes: Optional[str] = None,
    platform_scope: bool = False,
) -> Dict[str, Any]:
    """Susun baris audit tanpa menyimpan (dipakai alur transaksional, mis. Ubah Status)."""
    # platform_scope=True: aksi level platform (mis. branding) TIDAK dicatat di tenant
    # aktif Platform Admin agar tidak muncul di audit log tenant mana pun.
    entry = {
        "id": new_id(),
        "company_id": None if platform_scope else (company_id or (ctx.company_id if ctx else None)),
        "user_id": ctx.user_id if ctx else None,
        "user_name": ctx.user.get("full_name") if ctx else None,
        "user_email": ctx.user.get("email") if ctx else None,
        "module": module or resource_module(resource),
        "resource": resource,
        "action": action,
        "record_id": record_id,
        "record_label": record_label,
        "before_value": _stored(before),
        "after_value": _stored(after),
        "changed_fields": diff(before, after) if (before or after) else [],
        "notes": notes,
        "ip_address": ctx.ip if ctx else None,
        "user_agent": ctx.user_agent if ctx else None,
        "status": "active",
        "created_at": now(),
        "updated_at": now(),
        "created_by": ctx.user_id if ctx else None,
        "updated_by": ctx.user_id if ctx else None,
    }
    return entry


async def log_auth_event(
    action: str,
    user: Optional[Dict[str, Any]],
    email: str,
    ip: Optional[str],
    user_agent: Optional[str],
    company_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    db = get_db()
    await db.audit_logs.insert_one(
        {
            "id": new_id(),
            "company_id": company_id,
            "user_id": user.get("id") if user else None,
            "user_name": user.get("full_name") if user else None,
            "user_email": email,
            "module": "hr_core",
            "resource": "auth",
            "action": action,
            "record_id": user.get("id") if user else None,
            "record_label": email,
            "before_value": None,
            "after_value": None,
            "changed_fields": [],
            "notes": notes,
            "ip_address": ip,
            "user_agent": user_agent,
            "status": "active",
            "created_at": now(),
            "updated_at": now(),
            "created_by": user.get("id") if user else None,
            "updated_by": user.get("id") if user else None,
        }
    )
