"""Platform -> Tenant Management (Tenant Foundation Minimal).

Hierarki: PLATFORM KELOLAKITA -> TENANT -> TENANT ADMIN -> USER TENANT -> DATA TENANT.

- Tenant = baris pada tabel existing `companies` (TIDAK ada tabel tenant kedua).
- Semua endpoint di sini hanya untuk Platform Admin (role global `super_admin`),
  dicek di backend melalui `require_platform_admin`.
- Tenant hanya dapat Aktif / Nonaktif (soft-disable). TIDAK ada hard delete:
  data karyawan, payroll, dan histori tenant tidak pernah dihapus dari sini.
- Masa berlaku layanan (subscription) disimpan di kolom additive `companies`
  (start/end date, grace days, notes). Status ACTIVE/GRACE/EXPIRED DIHITUNG,
  terpisah dari status operasional. Hanya Platform Admin yang dapat mengubahnya.
"""
import secrets
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator

from ..core.audit import log_action
from ..core.config import settings
from ..core.db import NO_ID, audit_fields, get_db, new_id, now, serialize, serialize_list
from ..core.deps import AuthContext, require_platform_admin
from ..core.rbac import TENANT_ADMIN_ROLE
from ..core.tenant_subscription import SUBSCRIPTION_FIELDS, parse_date, subscription_info
from ..core.security import hash_password
from ..core.storage import StorageError, get_object
from .companies import ensure_company_settings, seed_company_modules

router = APIRouter(prefix="/platform", tags=["Platform - Tenant Management"])

TENANT_STATUSES = ("active", "inactive")


class SubscriptionFields(BaseModel):
    """Tanggal boleh kosong (tenant legacy/unlimited). Format YYYY-MM-DD."""

    subscription_start_date: Optional[str] = None
    subscription_end_date: Optional[str] = None
    grace_period_days: Optional[int] = Field(default=None, ge=0, le=3650)
    subscription_notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("subscription_start_date", "subscription_end_date", mode="before")
    @classmethod
    def _valid_date(cls, v):
        if v in (None, ""):
            return None
        d = parse_date(v)
        if d is None:
            raise ValueError("format tanggal harus YYYY-MM-DD")
        return d.isoformat()


PHONE_PATTERN = r"^[0-9+()\-\s]{6,20}$"


class TenantCreate(SubscriptionFields):
    """Provisioning tenant: Data Tenant + PIC + Email Utama + Tenant Admin pertama (satu proses)."""

    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    status: Literal["active", "inactive"] = "active"
    legal_name: Optional[str] = Field(default=None, max_length=255)
    # Email Utama Tenant = kolom existing companies.email (email kontak perusahaan).
    email: EmailStr
    pic_name: str = Field(min_length=2, max_length=255)
    pic_phone: str = Field(pattern=PHONE_PATTERN)
    # Tenant Admin pertama (WAJIB terbentuk bersama tenant).
    admin_use_primary_email: bool = True
    admin_full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    admin_email: Optional[EmailStr] = None


class TenantUpdate(SubscriptionFields):
    # extra diizinkan hanya agar percobaan mengubah `code` dapat ditolak TEGAS (400), bukan diabaikan.
    model_config = {"extra": "allow"}

    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    legal_name: Optional[str] = Field(default=None, max_length=255)
    status: Optional[Literal["active", "inactive"]] = None
    email: Optional[EmailStr] = None
    pic_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    pic_phone: Optional[str] = Field(default=None, pattern=PHONE_PATTERN)


def _normalize_subscription(merged: Dict[str, Any]) -> Dict[str, Any]:
    """Validasi gabungan (nilai lama + perubahan) lalu kembalikan nilai subscription final."""
    start = parse_date(merged.get("subscription_start_date"))
    end = parse_date(merged.get("subscription_end_date"))
    if start and end and end < start:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tanggal berakhir layanan tidak boleh lebih awal dari tanggal mulai layanan.",
        )
    grace = merged.get("grace_period_days")
    if grace is not None and int(grace) < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Grace period tidak boleh negatif.")
    if end and grace is None:
        # Default dari konfigurasi, lalu DISIMPAN per tenant (bukan hardcode saat dihitung).
        grace = settings.TENANT_DEFAULT_GRACE_PERIOD_DAYS
    notes = merged.get("subscription_notes")
    return {
        "subscription_start_date": start.isoformat() if start else None,
        "subscription_end_date": end.isoformat() if end else None,
        "grace_period_days": int(grace) if grace is not None else None,
        "subscription_notes": (notes.strip() or None) if isinstance(notes, str) else notes,
    }


class TenantAdminAssign(BaseModel):
    email: EmailStr
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)


class TenantUserAdd(TenantAdminAssign):
    role_key: str = Field(min_length=2, max_length=64)


def _public_user(u: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": u["id"], "full_name": u.get("full_name"), "email": u.get("email"), "status": u.get("status")}


async def _tenant_or_404(tenant_id: str) -> Dict[str, Any]:
    db = get_db()
    doc = await db.companies.find_one({"id": tenant_id}, NO_ID)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan.")
    return doc


async def _tenant_summary(c: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    memberships = await db.user_company_roles.find({"company_id": c["id"], "status": "active"}, NO_ID).to_list(5000)
    admin_ids = sorted({m["user_id"] for m in memberships if m.get("role_key") == TENANT_ADMIN_ROLE})
    admins: List[Dict[str, Any]] = []
    if admin_ids:
        admins = [_public_user(u) for u in await db.users.find({"id": {"$in": admin_ids}}, NO_ID).to_list(500)]
    return {
        "id": c["id"],
        "code": c.get("code"),
        "name": c.get("name"),
        "legal_name": c.get("legal_name"),
        "status": c.get("status"),
        "email": c.get("email"),
        "pic_name": c.get("pic_name"),
        "pic_phone": c.get("pic_phone"),
        "has_logo": bool(c.get("logo_path")),
        "logo_version": (c.get("logo_url") or "").rsplit("v=", 1)[-1] if c.get("logo_path") else None,
        "timezone": c.get("timezone"),
        "subscription": subscription_info(c),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "tenant_admins": sorted(admins, key=lambda a: (a.get("full_name") or "").lower()),
        "user_count": len({m["user_id"] for m in memberships}),
        "employee_count": await db.employees.count_documents({"company_id": c["id"], "status": {"$ne": "deleted"}}),
    }


# ------------------------------------------------------------------- list/detail
@router.get("/tenants")
async def list_tenants(
    q: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    subscription_filter: Optional[str] = Query(None, alias="subscription"),
    ctx: AuthContext = Depends(require_platform_admin()),
):
    db = get_db()
    query: Dict[str, Any] = {"status": {"$ne": "archived"}}
    if status_filter in TENANT_STATUSES:
        query["status"] = status_filter
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"code": {"$regex": q, "$options": "i"}}]
    rows = await db.companies.find(query, NO_ID).sort("name", 1).to_list(1000)
    items = [await _tenant_summary(c) for c in rows]
    if subscription_filter in ("active", "grace", "expired"):
        items = [i for i in items if i["subscription"]["status"] == subscription_filter]
    return {"items": serialize_list(items), "total": len(items)}


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, ctx: AuthContext = Depends(require_platform_admin())):
    return serialize(await _tenant_summary(await _tenant_or_404(tenant_id)))


# ------------------------------------------------------------------- create/edit
@router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, ctx: AuthContext = Depends(require_platform_admin())):
    """Buat Tenant + Data PIC + Email Utama + Tenant Admin pertama dalam SATU proses.

    Semua validasi dijalankan SEBELUM ada data yang ditulis. Jika salah satu langkah
    penulisan gagal, seluruh data yang sudah terbentuk dihapus kembali (kompensasi),
    sehingga tidak pernah ada tenant tanpa administrator utama.
    """
    db = get_db()
    code = payload.code.upper().strip()
    primary_email = payload.email.lower().strip()
    if payload.admin_use_primary_email:
        admin_email = primary_email
        admin_name = (payload.admin_full_name or payload.pic_name).strip()
    else:
        if not payload.admin_email or not payload.admin_full_name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Nama dan email Tenant Admin wajib diisi bila tidak memakai Email Utama Tenant.",
            )
        admin_email = payload.admin_email.lower().strip()
        admin_name = payload.admin_full_name.strip()

    # ---- validasi (belum ada penulisan)
    if await db.companies.count_documents({"code": code}):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Kode tenant '{code}' sudah digunakan.")
    if await db.users.find_one({"email": admin_email}, NO_ID):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Email {admin_email} sudah terdaftar sebagai pengguna. Gunakan email lain untuk Tenant Admin "
            "pertama; pengguna yang sudah ada dapat ditambahkan dari tab Users setelah tenant dibuat.",
        )
    sub = _normalize_subscription(payload.model_dump(include=set(SUBSCRIPTION_FIELDS)))

    tenant_id = new_id()
    admin_id = new_id()
    temp_password = secrets.token_urlsafe(12)
    doc = {
        "id": tenant_id,
        "company_id": tenant_id,
        "code": code,
        "name": payload.name.strip(),
        "legal_name": (payload.legal_name or "").strip() or None,
        "status": payload.status,
        "email": primary_email,
        "pic_name": payload.pic_name.strip(),
        "pic_phone": payload.pic_phone.strip(),
        "timezone": "Asia/Jakarta",
        "currency": "IDR",
        "fiscal_year_start_month": 1,
        **sub,
    }
    doc.update(audit_fields(ctx.user_id, creating=True))
    admin = {
        "id": admin_id,
        "company_id": None,
        "email": admin_email,
        "full_name": admin_name,
        "password_hash": hash_password(temp_password),
        "status": "active",
        "default_company_id": tenant_id,
        "must_change_password": True,
        "failed_login_attempts": 0,
        "is_demo_account": False,
        **audit_fields(ctx.user_id, creating=True),
    }
    membership = {
        "id": new_id(),
        "user_id": admin_id,
        "company_id": tenant_id,
        "role_key": TENANT_ADMIN_ROLE,
        "status": "active",
        **audit_fields(ctx.user_id, creating=True),
    }
    written: List[str] = []
    try:
        await db.companies.insert_one(dict(doc))
        written.append("company")
        await db.users.insert_one(dict(admin))
        written.append("user")
        await db.user_company_roles.insert_one(dict(membership))
        written.append("membership")
        # Reuse helper existing: modul inti aktif + pengaturan default tenant.
        await seed_company_modules(tenant_id, [], ctx.user_id)
        await ensure_company_settings(tenant_id, ctx.user_id)
    except Exception as exc:  # noqa: BLE001 - kompensasi lalu teruskan error
        await db.company_modules.delete_many({"company_id": tenant_id})
        await db.company_settings.delete_many({"company_id": tenant_id})
        if "membership" in written:
            await db.user_company_roles.delete_many({"id": membership["id"]})
        if "user" in written:
            await db.users.delete_many({"id": admin_id})
        if "company" in written:
            await db.companies.delete_many({"id": tenant_id})
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Tenant gagal dibuat; seluruh perubahan dibatalkan. Silakan coba lagi.",
        ) from exc

    clean = {k: v for k, v in doc.items() if k != "_id"}
    await log_action(ctx, "create", "tenant", tenant_id, doc["name"], after=clean, company_id=tenant_id,
                     module="platform", notes="Tenant dibuat oleh Platform Admin beserta Tenant Admin pertama")
    await log_action(ctx, "create", "user", admin_id, admin_email,
                     after={k: v for k, v in admin.items() if k != "password_hash"}, company_id=tenant_id,
                     notes="Akun Tenant Admin pertama dibuat saat provisioning tenant")
    await log_action(ctx, "assign_tenant_admin", "tenant", tenant_id, doc["name"],
                     after={"user_id": admin_id, "email": admin_email, "role_key": TENANT_ADMIN_ROLE,
                            "new_user": True, "first_admin": True,
                            "uses_primary_email": admin_email == primary_email},
                     company_id=tenant_id, module="platform")
    out = serialize(await _tenant_summary(clean))
    out["first_admin"] = {
        "user": _public_user(admin),
        "uses_primary_email": admin_email == primary_email,
        "temporary_password": temp_password,  # hanya dikembalikan sekali, tidak disimpan plaintext
    }
    return out


@router.put("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, payload: TenantUpdate, ctx: AuthContext = Depends(require_platform_admin())):
    db = get_db()
    before = await _tenant_or_404(tenant_id)
    sent = payload.model_dump(exclude_unset=True)
    patch: Dict[str, Any] = {}
    for k in ("name", "legal_name", "pic_name", "pic_phone"):
        if sent.get(k) is not None:
            patch[k] = sent[k].strip()
    if sent.get("email") is not None:
        patch["email"] = str(sent["email"]).lower().strip()
    if "code" in (payload.model_extra or {}):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kode tenant bersifat permanen dan tidak dapat diubah.")
    new_status = sent.get("status")
    if new_status and before.get("status") == "archived":
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant berstatus arsip tidak dapat diubah dari sini.")
    if new_status and new_status != before.get("status"):
        patch["status"] = new_status
    # Subscription: field yang dikirim (termasuk null untuk mengosongkan) digabung dengan nilai lama.
    sub_sent = {k: sent[k] for k in SUBSCRIPTION_FIELDS if k in sent}
    if sub_sent:
        merged = {k: before.get(k) for k in SUBSCRIPTION_FIELDS}
        merged.update(sub_sent)
        final = _normalize_subscription(merged)
        patch.update({k: v for k, v in final.items() if v != before.get(k)})
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    patch.update(audit_fields(ctx.user_id, creating=False))
    await db.companies.update_one({"id": tenant_id}, {"$set": patch})
    after = await _tenant_or_404(tenant_id)
    await log_action(ctx, "update", "tenant", tenant_id, after.get("name"), before=before, after=after,
                     company_id=tenant_id)
    if any(k in patch for k in SUBSCRIPTION_FIELDS):
        before_sub, after_sub = subscription_info(before), subscription_info(after)
        await log_action(
            ctx, "update_subscription", "tenant", tenant_id, after.get("name"),
            before={k: before.get(k) for k in SUBSCRIPTION_FIELDS} | {"computed_status": before_sub["status"]},
            after={k: after.get(k) for k in SUBSCRIPTION_FIELDS} | {"computed_status": after_sub["status"]},
            company_id=tenant_id,
            notes=f"Masa layanan: {before_sub['status']} -> {after_sub['status']}",
        )
    if "status" in patch:
        await log_action(ctx, "activate" if patch["status"] == "active" else "deactivate", "tenant", tenant_id,
                         after.get("name"), before={"status": before.get("status")},
                         after={"status": patch["status"]}, company_id=tenant_id)
    return serialize(await _tenant_summary(after))


# ------------------------------------------------------------- activate/deactivate
async def _set_status(tenant_id: str, new_status: str, ctx: AuthContext) -> Dict[str, Any]:
    db = get_db()
    before = await _tenant_or_404(tenant_id)
    if before.get("status") == "archived":
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant berstatus arsip tidak dapat diubah dari sini.")
    if before.get("status") == new_status:
        label = "aktif" if new_status == "active" else "nonaktif"
        raise HTTPException(status.HTTP_409_CONFLICT, f"Tenant sudah berstatus {label}.")
    # Soft-disable: hanya kolom status yang berubah. Data & histori tenant tidak disentuh.
    await db.companies.update_one(
        {"id": tenant_id}, {"$set": {"status": new_status, **audit_fields(ctx.user_id, creating=False)}}
    )
    after = await _tenant_or_404(tenant_id)
    action = "activate" if new_status == "active" else "deactivate"
    await log_action(ctx, action, "tenant", tenant_id, after.get("name"),
                     before={"status": before.get("status")}, after={"status": new_status}, company_id=tenant_id)
    return serialize(await _tenant_summary(after))


@router.post("/tenants/{tenant_id}/activate")
async def activate_tenant(tenant_id: str, ctx: AuthContext = Depends(require_platform_admin())):
    item = await _set_status(tenant_id, "active", ctx)
    return {"message": f"Tenant {item['name']} diaktifkan kembali. Seluruh data tetap tersedia.", "item": item}


@router.post("/tenants/{tenant_id}/deactivate")
async def deactivate_tenant(tenant_id: str, ctx: AuthContext = Depends(require_platform_admin())):
    item = await _set_status(tenant_id, "inactive", ctx)
    return {
        "message": f"Tenant {item['name']} dinonaktifkan. User tenant tidak dapat beroperasi; data tidak dihapus.",
        "item": item,
    }


# ------------------------------------------------------------------ tenant admin
@router.post("/tenants/{tenant_id}/admins", status_code=status.HTTP_201_CREATED)
async def assign_tenant_admin(
    tenant_id: str, payload: TenantAdminAssign, ctx: AuthContext = Depends(require_platform_admin())
):
    """Tunjuk Tenant Admin. User baru dibuat dengan kata sandi sementara ACAK
    (ditampilkan sekali, wajib diganti) - tidak ada password demo/hardcoded."""
    db = get_db()
    tenant = await _tenant_or_404(tenant_id)
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email}, NO_ID)
    temp_password: Optional[str] = None
    created = False
    if not user:
        if not payload.full_name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Email belum terdaftar. Isi nama lengkap agar akun Tenant Admin baru dapat dibuat.",
            )
        temp_password = secrets.token_urlsafe(12)
        user = {
            "id": new_id(),
            "company_id": None,
            "email": email,
            "full_name": payload.full_name.strip(),
            "password_hash": hash_password(temp_password),
            "status": "active",
            "default_company_id": tenant_id,
            "must_change_password": True,
            "failed_login_attempts": 0,
            "is_demo_account": False,
        }
        user.update(audit_fields(ctx.user_id, creating=True))
        await db.users.insert_one(dict(user))
        created = True
    elif user.get("status") != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Akun pengguna tersebut tidak aktif.")

    exists = await db.user_company_roles.find_one(
        {"user_id": user["id"], "company_id": tenant_id, "role_key": TENANT_ADMIN_ROLE, "status": "active"}, NO_ID
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{user.get('full_name')} sudah menjadi Tenant Admin tenant ini.")
    await db.user_company_roles.insert_one({
        "id": new_id(),
        "user_id": user["id"],
        "company_id": tenant_id,
        "role_key": TENANT_ADMIN_ROLE,
        "status": "active",
        **audit_fields(ctx.user_id, creating=True),
    })
    if not user.get("default_company_id"):
        await db.users.update_one({"id": user["id"]}, {"$set": {"default_company_id": tenant_id, "updated_at": now()}})
    await log_action(ctx, "assign_tenant_admin", "tenant", tenant_id, tenant.get("name"),
                     after={"user_id": user["id"], "email": email, "role_key": TENANT_ADMIN_ROLE, "new_user": created},
                     company_id=tenant_id)
    out: Dict[str, Any] = {
        "message": f"{user.get('full_name')} ditunjuk sebagai Tenant Admin {tenant.get('name')}.",
        "user": _public_user(user),
        "created": created,
        "tenant": serialize(await _tenant_summary(tenant)),
    }
    if temp_password:
        out["temporary_password"] = temp_password  # hanya dikembalikan sekali, tidak disimpan plaintext
    return out


@router.delete("/tenants/{tenant_id}/admins/{user_id}")
async def revoke_tenant_admin(tenant_id: str, user_id: str, ctx: AuthContext = Depends(require_platform_admin())):
    db = get_db()
    tenant = await _tenant_or_404(tenant_id)
    admins = await db.user_company_roles.find(
        {"company_id": tenant_id, "role_key": TENANT_ADMIN_ROLE, "status": "active"}, NO_ID
    ).to_list(500)
    admin_ids = {m["user_id"] for m in admins}
    if user_id in admin_ids and len(admin_ids) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Tenant harus memiliki minimal satu Tenant Admin aktif. Tunjuk Tenant Admin lain terlebih dahulu.",
        )
    res = await db.user_company_roles.delete_many(
        {"user_id": user_id, "company_id": tenant_id, "role_key": TENANT_ADMIN_ROLE}
    )
    if not getattr(res, "deleted_count", 0):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna tersebut bukan Tenant Admin tenant ini.")
    await log_action(ctx, "revoke_tenant_admin", "tenant", tenant_id, tenant.get("name"),
                     before={"user_id": user_id, "role_key": TENANT_ADMIN_ROLE}, company_id=tenant_id)
    return {"message": "Peran Tenant Admin dicabut. Akun pengguna dan peran lainnya tidak diubah.",
            "tenant": serialize(await _tenant_summary(tenant))}


@router.post("/tenants/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
async def add_tenant_user(tenant_id: str, payload: TenantUserAdd, ctx: AuthContext = Depends(require_platform_admin())):
    """Tambah user (Tenant Admin atau peran tenant lain) ke tenant dari tab Users Tenant Detail."""
    db = get_db()
    role_key = payload.role_key.strip()
    if role_key == TENANT_ADMIN_ROLE:
        return await assign_tenant_admin(tenant_id, TenantAdminAssign(email=payload.email, full_name=payload.full_name), ctx)
    if role_key == "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Peran Platform Admin tidak dapat diberikan dari tenant.")
    role = await db.roles.find_one({"key": role_key}, NO_ID)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Peran tidak ditemukan.")
    tenant = await _tenant_or_404(tenant_id)
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email}, NO_ID)
    temp_password: Optional[str] = None
    created = False
    if not user:
        if not payload.full_name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Email belum terdaftar. Isi nama lengkap agar akun baru dapat dibuat.")
        temp_password = secrets.token_urlsafe(12)
        user = {
            "id": new_id(), "company_id": None, "email": email, "full_name": payload.full_name.strip(),
            "password_hash": hash_password(temp_password), "status": "active", "default_company_id": tenant_id,
            "must_change_password": True, "failed_login_attempts": 0, "is_demo_account": False,
            **audit_fields(ctx.user_id, creating=True),
        }
        await db.users.insert_one(dict(user))
        created = True
    elif user.get("status") != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Akun pengguna tersebut tidak aktif.")
    if await db.user_company_roles.find_one({"user_id": user["id"], "company_id": tenant_id, "role_key": role_key}, NO_ID):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{user.get('full_name')} sudah memiliki peran tersebut di tenant ini.")
    await db.user_company_roles.insert_one({
        "id": new_id(), "user_id": user["id"], "company_id": tenant_id, "role_key": role_key, "status": "active",
        **audit_fields(ctx.user_id, creating=True),
    })
    if created:
        await log_action(ctx, "create", "user", user["id"], email,
                         after={k: v for k, v in user.items() if k != "password_hash"}, company_id=tenant_id,
                         notes="Akun dibuat Platform Admin dari Tenant Detail")
    await log_action(ctx, "assign_role", "tenant", tenant_id, tenant.get("name"),
                     after={"user_id": user["id"], "email": email, "role_key": role_key, "new_user": created},
                     company_id=tenant_id, module="platform")
    out: Dict[str, Any] = {
        "message": f"{user.get('full_name')} ditambahkan ke {tenant.get('name')} sebagai {role.get('name')}.",
        "user": _public_user(user), "created": created,
    }
    if temp_password:
        out["temporary_password"] = temp_password
    return out


@router.get("/tenants/{tenant_id}/users")
async def list_tenant_users(tenant_id: str, ctx: AuthContext = Depends(require_platform_admin())):
    db = get_db()
    await _tenant_or_404(tenant_id)
    memberships = await db.user_company_roles.find({"company_id": tenant_id, "status": "active"}, NO_ID).to_list(5000)
    by_user: Dict[str, List[str]] = {}
    for m in memberships:
        by_user.setdefault(m["user_id"], []).append(m.get("role_key"))
    users = await db.users.find({"id": {"$in": list(by_user)}}, NO_ID).to_list(5000) if by_user else []
    roles = {r["key"]: r.get("name") for r in await db.roles.find({}, NO_ID).to_list(500)}
    items = []
    for u in users:
        keys = sorted(by_user.get(u["id"], []))
        items.append({
            **_public_user(u),
            "role_keys": keys,
            "role_names": [roles.get(k, k) for k in keys],
            "is_tenant_admin": TENANT_ADMIN_ROLE in keys,
            "last_login_at": u.get("last_login_at"),
            "must_change_password": bool(u.get("must_change_password")),
            "created_at": u.get("created_at"),
        })
    items.sort(key=lambda x: (not x["is_tenant_admin"], (x.get("full_name") or "").lower()))
    return {"items": serialize_list(items), "total": len(items)}


@router.post("/tenants/{tenant_id}/users/{user_id}/reset-password")
async def reset_tenant_user_password(
    tenant_id: str, user_id: str, ctx: AuthContext = Depends(require_platform_admin())
):
    """Reset password user tenant (Tenant Detail -> Users).

    - Password sementara baru di-generate server, disimpan HANYA sebagai hash,
      dan dikembalikan SEKALI pada respons ini (tidak dapat dilihat ulang).
    - User wajib mengganti password pada login berikutnya (`must_change_password`).
    - Password lama tidak ditampilkan dan langsung tidak berlaku.
    - Audit log mencatat aksi reset TANPA nilai password.
    """
    db = get_db()
    tenant = await _tenant_or_404(tenant_id)
    membership = await db.user_company_roles.find_one(
        {"user_id": user_id, "company_id": tenant_id, "status": "active"}, NO_ID
    )
    if not membership:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna tersebut bukan anggota tenant ini.")
    if await db.user_company_roles.find_one({"user_id": user_id, "role_key": "super_admin"}, NO_ID):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Password Platform Admin tidak dapat direset dari Tenant Detail."
        )
    user = await db.users.find_one({"id": user_id}, NO_ID)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna tidak ditemukan.")
    if user.get("status") != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Akun pengguna tersebut tidak aktif.")
    temp_password = secrets.token_urlsafe(12)
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password_hash": hash_password(temp_password),
            "must_change_password": True,
            "failed_login_attempts": 0,
            "locked_until": None,
            **audit_fields(ctx.user_id, creating=False),
        }},
    )
    await log_action(ctx, "reset_password", "user", user_id, user.get("email"), company_id=tenant_id,
                     module="platform",
                     notes=f"Password direset Platform Admin untuk tenant {tenant.get('name')}; "
                           "wajib ganti password saat login berikutnya")
    return {
        "message": f"Password {user.get('full_name') or user.get('email')} berhasil direset.",
        "user": _public_user(user),
        "temporary_password": temp_password,  # hanya dikembalikan sekali, tidak disimpan plaintext
    }



@router.get("/tenants/{tenant_id}/activities")
async def list_tenant_activities(
    tenant_id: str, limit: int = Query(50, ge=1, le=200), ctx: AuthContext = Depends(require_platform_admin())
):
    db = get_db()
    await _tenant_or_404(tenant_id)
    rows = await db.audit_logs.find({"company_id": tenant_id}, NO_ID).sort("created_at", -1).limit(limit).to_list(limit)
    keep = ("id", "action", "resource", "module", "record_label", "user_name", "user_email", "notes",
            "changed_fields", "created_at", "ip_address")
    return {"items": serialize_list([{k: r.get(k) for k in keep} for r in rows]), "total": len(rows)}


@router.get("/tenants/{tenant_id}/logo")
async def get_tenant_logo(tenant_id: str, ctx: AuthContext = Depends(require_platform_admin())):
    tenant = await _tenant_or_404(tenant_id)
    path = tenant.get("logo_path")
    if not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant belum mengunggah logo.")
    try:
        data, content_type = get_object(path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


@router.get("/tenant-roles")
async def list_tenant_roles(ctx: AuthContext = Depends(require_platform_admin())):
    db = get_db()
    rows = await db.roles.find({}, NO_ID).sort("sort_order", 1).to_list(200)
    items = [{"key": r["key"], "name": r.get("name")} for r in rows if r.get("key") != "super_admin"]
    return {"items": items}


@router.get("/dashboard")
async def platform_dashboard(ctx: AuthContext = Depends(require_platform_admin())):
    """Ringkasan Platform Dashboard - seluruhnya dari data nyata (tanpa dummy)."""
    db = get_db()
    rows = await db.companies.find({"status": {"$ne": "archived"}}, NO_ID).sort("name", 1).to_list(2000)
    infos = [(c, subscription_info(c)) for c in rows]
    memberships = await db.user_company_roles.find({"status": "active"}, NO_ID).to_list(20000)
    tenant_ids = {c["id"] for c in rows}
    tenant_users = {m["user_id"] for m in memberships if m.get("company_id") in tenant_ids}
    admins_per_tenant: Dict[str, int] = {}
    for m in memberships:
        if m.get("role_key") == TENANT_ADMIN_ROLE and m.get("company_id") in tenant_ids:
            admins_per_tenant[m["company_id"]] = admins_per_tenant.get(m["company_id"], 0) + 1

    def brief(c, info):
        return {"id": c["id"], "code": c.get("code"), "name": c.get("name"), "status": c.get("status"),
                "subscription": info, "has_logo": bool(c.get("logo_path"))}

    expiring = sorted(
        [brief(c, i) for c, i in infos
         if i["status"] == "active" and i["days_remaining"] is not None and i["days_remaining"] <= 30],
        key=lambda x: x["subscription"]["days_remaining"],
    )
    attention = [brief(c, i) for c, i in infos if i["status"] in ("grace", "expired") or c.get("status") != "active"]
    recent = sorted(rows, key=lambda c: str(c.get("created_at") or ""), reverse=True)[:5]
    activity_rows = await db.audit_logs.find(
        {"resource": {"$in": ["tenant", "platform_branding"]}}, NO_ID
    ).sort("created_at", -1).limit(12).to_list(12)
    names = {c["id"]: c.get("name") for c in rows}
    activities = [{
        "id": a.get("id"), "action": a.get("action"), "resource": a.get("resource"),
        "record_label": a.get("record_label"), "tenant_name": names.get(a.get("company_id")),
        "user_name": a.get("user_name"), "notes": a.get("notes"), "created_at": a.get("created_at"),
    } for a in activity_rows]
    return serialize({
        "totals": {
            "tenants": len(rows),
            "operational_active": sum(1 for c in rows if c.get("status") == "active"),
            "operational_inactive": sum(1 for c in rows if c.get("status") != "active"),
            "subscription_active": sum(1 for _, i in infos if i["status"] == "active" and not i["unlimited"]),
            "subscription_unlimited": sum(1 for _, i in infos if i["unlimited"]),
            "subscription_grace": sum(1 for _, i in infos if i["status"] == "grace"),
            "subscription_expired": sum(1 for _, i in infos if i["status"] == "expired"),
            "tenant_users": len(tenant_users),
            "employees": await db.employees.count_documents(
                {"company_id": {"$in": list(tenant_ids)}, "status": {"$ne": "deleted"}}) if tenant_ids else 0,
            "tenants_without_admin": sum(1 for c in rows if not admins_per_tenant.get(c["id"])),
        },
        "expiring_soon": expiring,
        "needs_attention": attention,
        "recent_tenants": [brief(c, subscription_info(c)) | {"created_at": c.get("created_at")} for c in recent],
        "recent_activities": activities,
    })
