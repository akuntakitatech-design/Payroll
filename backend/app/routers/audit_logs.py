from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pymongo import DESCENDING

from ..core.db import NO_ID, get_db, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.rbac import MODULES, RESOURCES

router = APIRouter(prefix="/audit-logs", tags=["Audit Log"])

ACTION_LABELS = {
    "login": "Login",
    "login_failed": "Login Gagal",
    "login_blocked": "Login Diblokir",
    "logout": "Logout",
    "create": "Tambah",
    "update": "Ubah",
    "delete": "Hapus",
    "upload": "Unggah",
    "activate": "Aktifkan Modul",
    "deactivate": "Nonaktifkan Modul",
    "status_active": "Aktifkan",
    "status_inactive": "Nonaktifkan",
    "status_archived": "Arsipkan",
    "switch_company": "Ganti Perusahaan",
    "update_permissions": "Ubah Hak Akses",
    "grant_access": "Beri Akses",
    "revoke_access": "Cabut Akses",
    "change_password": "Ubah Kata Sandi",
    "export": "Ekspor",
}


@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(require_permission("audit_log", "view"))):
    db = get_db()
    users = await db.user_company_roles.find(
        {"company_id": ctx.company_id, "status": "active"}, NO_ID
    ).to_list(5000)
    user_ids = sorted({u["user_id"] for u in users})
    rows = serialize_list(
        await db.users.find({"id": {"$in": user_ids}}, NO_ID).sort("full_name", 1).to_list(2000)
    )
    return {
        "actions": [{"key": k, "label": v} for k, v in ACTION_LABELS.items()],
        "modules": [{"key": m["key"], "label": m["name"]} for m in MODULES],
        "resources": [{"key": k, "label": v[0]} for k, v in RESOURCES.items()],
        "users": [{"id": u["id"], "name": u.get("full_name"), "email": u.get("email")} for u in rows],
    }


@router.get("")
async def list_audit_logs(
    q: Optional[str] = None,
    module: Optional[str] = None,
    resource: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    limit: int = 25,
    ctx: AuthContext = Depends(require_permission("audit_log", "view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id}
    for key, value in (("module", module), ("resource", resource), ("action", action), ("user_id", user_id)):
        if value:
            query[key] = value
    if q:
        query["$or"] = [
            {"record_label": {"$regex": q, "$options": "i"}},
            {"user_name": {"$regex": q, "$options": "i"}},
            {"user_email": {"$regex": q, "$options": "i"}},
            {"record_id": {"$regex": q, "$options": "i"}},
        ]
    date_query: Dict[str, Any] = {}
    if date_from:
        try:
            date_query["$gte"] = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    if date_to:
        try:
            end = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            date_query["$lte"] = end + timedelta(days=1)
        except Exception:
            pass
    if date_query:
        query["created_at"] = date_query

    page, limit = max(1, page), min(100, max(1, limit))
    total = await db.audit_logs.count_documents(query)
    rows = serialize_list(
        await db.audit_logs.find(query, NO_ID)
        .sort("created_at", DESCENDING)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    for r in rows:
        r["action_label"] = ACTION_LABELS.get(r.get("action"), r.get("action"))
        res = RESOURCES.get(r.get("resource"))
        r["resource_label"] = res[0] if res else r.get("resource")
    return {
        "items": rows,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/export")
async def export_audit_logs(
    module: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 2000,
    ctx: AuthContext = Depends(require_permission("audit_log", "export")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id}
    if module:
        query["module"] = module
    if action:
        query["action"] = action
    rows = serialize_list(
        await db.audit_logs.find(query, NO_ID).sort("created_at", DESCENDING).to_list(min(5000, limit))
    )
    return {"items": rows, "total": len(rows), "generated_at": datetime.now(timezone.utc)}
