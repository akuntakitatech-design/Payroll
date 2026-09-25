from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, Response, UploadFile, status

from ..core.audit import log_action
from ..core.branding_assets import is_tenant_logo_path, read_image_upload, tenant_logo_path
from ..core.storage import StorageError, delete_object, get_object, put_object
from ..core.db import NO_ID, audit_fields, get_db, new_id, now, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, get_auth_optional_company, require_permission, require_super_admin
from ..core.rbac import MODULES
from ..core.tenant_subscription import SUBSCRIPTION_FIELDS
from ..schemas import CompanyCreate, CompanySettingsUpdate, CompanyUpdate, ModuleToggleRequest

router = APIRouter(tags=["Perusahaan"])

# Identitas & status tenant: hanya Platform Admin yang boleh mengubah.
TENANT_IDENTITY_FIELDS = ("name", "legal_name", "status")

DEFAULT_SETTINGS = {
    "employee_id_prefix": "EMP",
    "employee_id_next_number": 1,
    "date_format": "DD/MM/YYYY",
    "number_format": "1.000,00",
    "default_language": "id",
    "week_start": "monday",
    "notification_email": None,
    "enable_email_notification": True,
    "enable_audit_retention_days": 730,
    "require_two_factor": False,
    "password_min_length": 8,
    "session_timeout_minutes": 480,
    "payroll_bank_name": None,
    "payroll_bank_account_number": None,
    "payroll_bank_account_name": None,
    "payroll_transfer_note": "Gaji {periode}",
}


async def ensure_company_settings(company_id: str, user_id: Optional[str]) -> Dict[str, Any]:
    db = get_db()
    doc = await db.company_settings.find_one({"company_id": company_id}, NO_ID)
    if doc:
        return serialize(doc)
    doc = {"id": new_id(), "company_id": company_id, "status": "active", **DEFAULT_SETTINGS}
    doc.update(audit_fields(user_id, creating=True))
    await db.company_settings.insert_one(dict(doc))
    return {k: v for k, v in doc.items() if k != "_id"}


async def seed_company_modules(company_id: str, active_keys: List[str], user_id: Optional[str]) -> None:
    db = get_db()
    for mod in MODULES:
        exists = await db.company_modules.find_one(
            {"company_id": company_id, "module_key": mod["key"]}, NO_ID
        )
        if exists:
            continue
        doc = {
            "id": new_id(),
            "company_id": company_id,
            "module_key": mod["key"],
            "is_active": mod["is_core"] or mod["key"] in active_keys,
            "status": "active",
            "activated_at": now(),
            "notes": None,
        }
        doc.update(audit_fields(user_id, creating=True))
        await db.company_modules.insert_one(dict(doc))


# ----------------------------------------------------------------- companies
@router.get("/companies")
async def list_companies(
    q: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    limit: int = 20,
    ctx: AuthContext = Depends(get_auth_optional_company),
):
    db = get_db()
    query: Dict[str, Any] = {}
    if not ctx.is_super_admin:
        rows = await db.user_company_roles.find({"user_id": ctx.user_id, "status": "active"}, NO_ID).to_list(500)
        ids = sorted({r["company_id"] for r in rows if r.get("company_id")})
        query["id"] = {"$in": ids}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"code": {"$regex": q, "$options": "i"}},
            {"city": {"$regex": q, "$options": "i"}},
        ]
    if status_filter:
        query["status"] = status_filter
    page, limit = max(1, page), min(100, max(1, limit))
    total = await db.companies.count_documents(query)
    items = (
        await db.companies.find(query, NO_ID)
        .sort("name", 1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    for c in items:
        c["employee_count"] = 0
        c["active_module_count"] = await db.company_modules.count_documents(
            {"company_id": c["id"], "is_active": True}
        )
        c["user_count"] = len(
            {
                r["user_id"]
                for r in await db.user_company_roles.find(
                    {"company_id": c["id"], "status": "active"}, NO_ID
                ).to_list(1000)
            }
        )
    return {
        "items": serialize_list(items),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


@router.post("/companies", status_code=status.HTTP_201_CREATED)
async def create_company(payload: CompanyCreate, ctx: AuthContext = Depends(require_super_admin())):
    db = get_db()
    code = payload.code.upper().strip()
    if await db.companies.count_documents({"code": code}):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Kode perusahaan '{code}' sudah digunakan.")
    data = payload.model_dump(exclude={"modules"})
    data["code"] = code
    doc = {"id": new_id(), "company_id": None, "status": "active", **data}
    doc.update(audit_fields(ctx.user_id, creating=True))
    doc["company_id"] = doc["id"]
    await db.companies.insert_one(dict(doc))
    await seed_company_modules(doc["id"], payload.modules or [], ctx.user_id)
    await ensure_company_settings(doc["id"], ctx.user_id)
    clean = {k: v for k, v in doc.items() if k != "_id"}
    await log_action(ctx, "create", "company", doc["id"], doc["name"], after=clean, company_id=doc["id"])
    return clean


@router.get("/companies/current")
async def current_company(ctx: AuthContext = Depends(get_auth)):
    db = get_db()
    settings_doc = await ensure_company_settings(ctx.company_id, ctx.user_id)
    counts = {}
    for coll, key in [
        ("branches", "branches"),
        ("work_locations", "work_locations"),
        ("departments", "departments"),
        ("divisions", "divisions"),
        ("positions", "positions"),
        ("job_grades", "job_grades"),
        ("cost_centers", "cost_centers"),
        ("projects", "projects"),
    ]:
        counts[key] = await db[coll].count_documents(
            {"company_id": ctx.company_id, "status": "active"}
        )
    return {"company": ctx.company, "settings": settings_doc, "counts": counts}


@router.put("/companies/current")
async def update_current_company(
    payload: CompanyUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_permission("company", "edit")),
):
    db = get_db()
    # Masa layanan (subscription) hanya dikelola Platform Admin lewat Platform -> Tenant Management.
    # Percobaan langsung lewat endpoint tenant ditolak tegas (bukan diabaikan diam-diam).
    try:
        raw = await request.json()
    except Exception:
        raw = {}
    if isinstance(raw, dict) and any(k in raw for k in SUBSCRIPTION_FIELDS):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Masa layanan tenant hanya dapat diubah oleh Platform Admin (Platform > Tenant Management).",
        )
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    # Logo tenant hanya lewat upload (POST /companies/current/logo) - tidak menerima URL manual.
    patch.pop("logo_url", None)
    patch.pop("logo_path", None)
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    before = await db.companies.find_one({"id": ctx.company_id}, NO_ID)
    # Identitas & status tenant hanya boleh diubah Platform Admin (Platform -> Tenant Management).
    # Field profil operasional (alamat, NPWP, logo, zona waktu, dst.) tetap dikelola tenant.
    if not ctx.is_platform_admin:
        locked = [k for k in TENANT_IDENTITY_FIELDS if k in patch and patch[k] != (before or {}).get(k)]
        if locked:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Nama tenant, nama badan hukum, dan status tenant hanya dapat diubah oleh Platform Admin.",
            )
        for k in TENANT_IDENTITY_FIELDS:
            patch.pop(k, None)
    patch.update(audit_fields(ctx.user_id, creating=False))
    await db.companies.update_one({"id": ctx.company_id}, {"$set": patch})
    after = serialize(await db.companies.find_one({"id": ctx.company_id}, NO_ID))
    await log_action(ctx, "update", "company", ctx.company_id, after.get("name"), before=before, after=after)
    return after


# ------------------------------------------------------------- tenant logo
# Semua endpoint logo tenant bekerja pada ctx.company_id (tenant aktif hasil token),
# TIDAK menerima company_id dari klien -> Tenant A tidak mungkin membaca/mengubah logo Tenant B.
@router.get("/companies/current/logo")
async def get_current_company_logo(ctx: AuthContext = Depends(get_auth)):
    db = get_db()
    company = await db.companies.find_one({"id": ctx.company_id}, NO_ID)
    path = (company or {}).get("logo_path")
    if not path or not is_tenant_logo_path(ctx.company_id, path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perusahaan belum mengunggah logo.")
    try:
        data, content_type = get_object(path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


@router.post("/companies/current/logo")
async def upload_current_company_logo(
    file: UploadFile = File(...), ctx: AuthContext = Depends(require_permission("company", "edit"))
):
    db = get_db()
    data, ext, mime = await read_image_upload(file)
    before = await db.companies.find_one({"id": ctx.company_id}, NO_ID) or {}
    old_path = before.get("logo_path")
    path = tenant_logo_path(ctx.company_id, ext)
    try:
        put_object(path, data, mime)
    except StorageError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    version = new_id()[:8]
    patch = {"logo_path": path, "logo_url": f"/api/companies/current/logo?v={version}"}
    patch.update(audit_fields(ctx.user_id, creating=False))
    await db.companies.update_one({"id": ctx.company_id}, {"$set": patch})
    if old_path and old_path != path and is_tenant_logo_path(ctx.company_id, old_path):
        delete_object(old_path)
    await log_action(ctx, "replace_logo" if old_path else "upload_logo", "company", ctx.company_id,
                     before.get("name"), before={"logo_path": old_path},
                     after={"logo_path": path, "size": len(data), "content_type": mime})
    after = serialize(await db.companies.find_one({"id": ctx.company_id}, NO_ID))
    return {"message": "Logo perusahaan berhasil disimpan.", "company": after}


@router.delete("/companies/current/logo")
async def delete_current_company_logo(ctx: AuthContext = Depends(require_permission("company", "edit"))):
    db = get_db()
    before = await db.companies.find_one({"id": ctx.company_id}, NO_ID) or {}
    old_path = before.get("logo_path")
    if not old_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perusahaan belum mengunggah logo.")
    await db.companies.update_one(
        {"id": ctx.company_id},
        {"$set": {"logo_path": None, "logo_url": None, **audit_fields(ctx.user_id, creating=False)}},
    )
    if is_tenant_logo_path(ctx.company_id, old_path):
        delete_object(old_path)
    await log_action(ctx, "delete_logo", "company", ctx.company_id, before.get("name"),
                     before={"logo_path": old_path}, after={"logo_path": None})
    after = serialize(await db.companies.find_one({"id": ctx.company_id}, NO_ID))
    return {"message": "Logo perusahaan dihapus. Placeholder default akan ditampilkan.", "company": after}


@router.put("/companies/current/settings")
async def update_settings(
    payload: CompanySettingsUpdate, ctx: AuthContext = Depends(require_permission("settings", "config"))
):
    db = get_db()
    before = await ensure_company_settings(ctx.company_id, ctx.user_id)
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    patch.update(audit_fields(ctx.user_id, creating=False))
    await db.company_settings.update_one({"company_id": ctx.company_id}, {"$set": patch})
    after = serialize(await db.company_settings.find_one({"company_id": ctx.company_id}, NO_ID))
    await log_action(ctx, "update", "settings", after["id"], "Pengaturan Perusahaan", before=before, after=after)
    return after


# ------------------------------------------------------------------- modules
@router.get("/modules")
async def list_modules(ctx: AuthContext = Depends(get_auth)):
    db = get_db()
    rows = await db.company_modules.find({"company_id": ctx.company_id}, NO_ID).to_list(200)
    by_key = {r["module_key"]: r for r in rows}
    catalog = await db.modules.find({}, NO_ID).sort("sort_order", 1).to_list(200)
    out = []
    for mod in catalog:
        row = by_key.get(mod["key"], {})
        out.append(
            {
                **mod,
                "is_active": bool(row.get("is_active")) or mod.get("is_core", False),
                "company_module_id": row.get("id"),
                "activated_at": row.get("activated_at"),
                "notes": row.get("notes"),
                "can_toggle": not mod.get("is_core", False),
            }
        )
    return {"items": out, "total": len(out)}


@router.put("/modules/toggle")
async def toggle_module(
    payload: ModuleToggleRequest, ctx: AuthContext = Depends(require_permission("module", "config"))
):
    db = get_db()
    mod = await db.modules.find_one({"key": payload.module_key}, NO_ID)
    if not mod:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modul tidak ditemukan.")
    if mod.get("is_core") and not payload.is_active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Modul HR Core adalah modul dasar dan tidak dapat dinonaktifkan.",
        )
    before = await db.company_modules.find_one(
        {"company_id": ctx.company_id, "module_key": payload.module_key}, NO_ID
    )
    if before:
        patch = {"is_active": payload.is_active, "notes": payload.notes}
        if payload.is_active:
            patch["activated_at"] = now()
        else:
            patch["deactivated_at"] = now()
        patch.update(audit_fields(ctx.user_id, creating=False))
        await db.company_modules.update_one(
            {"company_id": ctx.company_id, "module_key": payload.module_key}, {"$set": patch}
        )
    else:
        doc = {
            "id": new_id(),
            "company_id": ctx.company_id,
            "module_key": payload.module_key,
            "is_active": payload.is_active,
            "status": "active",
            "activated_at": now() if payload.is_active else None,
            "notes": payload.notes,
        }
        doc.update(audit_fields(ctx.user_id, creating=True))
        await db.company_modules.insert_one(dict(doc))
    after = serialize(await db.company_modules.find_one(
        {"company_id": ctx.company_id, "module_key": payload.module_key}, NO_ID
    ))
    await log_action(
        ctx,
        "activate" if payload.is_active else "deactivate",
        "module",
        after["id"],
        mod["name"],
        before=before,
        after=after,
    )
    return {
        "message": f"Modul {mod['name']} berhasil " + ("diaktifkan." if payload.is_active else "dinonaktifkan."),
        "item": after,
    }
