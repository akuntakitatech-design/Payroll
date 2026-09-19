"""Central audit trail. Records who changed what, when, and the before/after values."""
from typing import Any, Dict, List, Optional

from .db import NO_ID, get_db, new_id, now
from .rbac import resource_module

SENSITIVE_KEYS = {"password_hash", "password", "refresh_token"}


def _sanitize(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    return {k: v for k, v in data.items() if k not in SENSITIVE_KEYS and k != "_id"}


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
) -> Dict[str, Any]:
    db = get_db()
    entry = {
        "id": new_id(),
        "company_id": company_id or (ctx.company_id if ctx else None),
        "user_id": ctx.user_id if ctx else None,
        "user_name": ctx.user.get("full_name") if ctx else None,
        "user_email": ctx.user.get("email") if ctx else None,
        "module": module or resource_module(resource),
        "resource": resource,
        "action": action,
        "record_id": record_id,
        "record_label": record_label,
        "before_value": _sanitize(before),
        "after_value": _sanitize(after),
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
    await db.audit_logs.insert_one(dict(entry))
    return {k: v for k, v in entry.items() if k != "_id"}


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
