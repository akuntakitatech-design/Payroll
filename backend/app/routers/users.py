from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..core.audit import log_action
from ..core.db import NO_ID, audit_fields, get_db, new_id, now, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.rbac import PLATFORM_ADMIN_ROLE, PLATFORM_ONLY_PERMISSIONS, WILDCARD
from ..core.security import hash_password
from ..schemas import RoleCreate, RolePermissionUpdate, RoleUpdate, UserCreate, UserUpdate

router = APIRouter(tags=["Pengguna & Peran"])

PUBLIC_EXCLUDE = ("password_hash", "_id", "failed_login_attempts", "locked_until")


def _public(user: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in user.items() if k not in PUBLIC_EXCLUDE}


# ------------------------------------------------------- tenant isolation (roles)
# Peran global (company_id NULL, termasuk peran sistem) berlaku untuk SEMUA tenant,
# sehingga hanya Platform Admin yang boleh mengubahnya. Peran buatan tenant
# (company_id = tenant) hanya terlihat & dapat dikelola di tenant tersebut.
def _role_visible(ctx: AuthContext, role: Dict[str, Any]) -> bool:
    return role.get("company_id") in (None, ctx.company_id)


def _guard_role_change(ctx: AuthContext, role: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not role or not _role_visible(ctx, role):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Peran tidak ditemukan.")
    if role.get("company_id") is None and not ctx.is_platform_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Peran sistem/global berlaku untuk semua tenant dan hanya dapat diubah oleh Platform Admin. "
            "Buat peran khusus tenant bila membutuhkan hak akses berbeda.",
        )
    return role


async def _is_platform_user(user_id: str) -> bool:
    db = get_db()
    rows = await db.user_company_roles.find(
        {"user_id": user_id, "role_key": PLATFORM_ADMIN_ROLE, "status": "active"}, NO_ID
    ).to_list(10)
    return any(r.get("company_id") is None for r in rows)


async def _guard_platform_user(ctx: AuthContext, user_id: str) -> None:
    if not ctx.is_platform_admin and await _is_platform_user(user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Akun Platform Admin hanya dapat dikelola oleh Platform Admin."
        )


async def _has_other_tenant_membership(ctx: AuthContext, user_id: str) -> bool:
    """True bila akun juga aktif di tenant lain (akun login bersifat global)."""
    db = get_db()
    rows = await db.user_company_roles.find({"user_id": user_id, "status": "active"}, NO_ID).to_list(500)
    return any(r.get("company_id") not in (None, ctx.company_id) for r in rows)


async def _assignable_role_keys(ctx: AuthContext) -> List[str]:
    db = get_db()
    rows = await db.roles.find({"status": "active"}, NO_ID).sort("sort_order", 1).to_list(500)
    keys = [r["key"] for r in rows if _role_visible(ctx, r)]
    if not ctx.is_super_admin:
        keys = [k for k in keys if k != "super_admin"]
    return keys


# ------------------------------------------------------------------- users
@router.get("/users")
async def list_users(
    q: Optional[str] = None,
    role_key: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    limit: int = 20,
    ctx: AuthContext = Depends(require_permission("user", "view")),
):
    db = get_db()
    memberships = await db.user_company_roles.find(
        {"company_id": ctx.company_id, "status": "active"}, NO_ID
    ).to_list(5000)
    roles_by_user: Dict[str, List[str]] = {}
    for m in memberships:
        roles_by_user.setdefault(m["user_id"], []).append(m["role_key"])

    user_ids = list(roles_by_user.keys())
    if role_key:
        user_ids = [uid for uid in user_ids if role_key in roles_by_user[uid]]

    query: Dict[str, Any] = {"id": {"$in": user_ids}}
    if q:
        query["$or"] = [
            {"full_name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"employee_number": {"$regex": q, "$options": "i"}},
        ]
    if status_filter:
        query["status"] = status_filter

    page, limit = max(1, page), min(100, max(1, limit))
    total = await db.users.count_documents(query)
    rows = (
        await db.users.find(query, NO_ID)
        .sort("full_name", 1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    items = []
    for u in serialize_list(rows):
        item = _public(u)
        item["role_keys"] = sorted(roles_by_user.get(u["id"], []))
        items.append(item)
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, ctx: AuthContext = Depends(require_permission("user", "create"))):
    db = get_db()
    email = payload.email.lower().strip()
    if await db.users.count_documents({"email": email}):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Email '{email}' sudah terdaftar. Gunakan menu Pengguna untuk menambahkan peran pada akun yang ada.",
        )
    assignable = await _assignable_role_keys(ctx)
    invalid = [r for r in payload.role_keys if r not in assignable]
    if invalid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Peran berikut tidak dapat Anda berikan: {', '.join(invalid)}.",
        )
    if payload.is_super_admin and not ctx.is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Super Admin yang dapat membuat Super Admin.")

    doc = {
        "id": new_id(),
        "company_id": None,
        "email": email,
        "full_name": payload.full_name.strip(),
        "password_hash": hash_password(payload.password),
        "phone": payload.phone,
        "job_title": payload.job_title,
        "employee_number": payload.employee_number,
        "status": "active",
        "default_company_id": ctx.company_id,
        "last_login_at": None,
        "failed_login_attempts": 0,
        "locked_until": None,
        "must_change_password": True,
    }
    doc.update(audit_fields(ctx.user_id, creating=True))
    await db.users.insert_one(dict(doc))

    role_keys = list(payload.role_keys) or ["employee"]
    for rk in role_keys:
        await db.user_company_roles.insert_one(
            {
                "id": new_id(),
                "user_id": doc["id"],
                "company_id": ctx.company_id,
                "role_key": rk,
                "status": "active",
                **audit_fields(ctx.user_id, creating=True),
            }
        )
    if payload.is_super_admin and ctx.is_super_admin:
        await db.user_company_roles.insert_one(
            {
                "id": new_id(),
                "user_id": doc["id"],
                "company_id": None,
                "role_key": "super_admin",
                "status": "active",
                **audit_fields(ctx.user_id, creating=True),
            }
        )
    out = _public({k: v for k, v in doc.items() if k != "_id"})
    out["role_keys"] = role_keys
    await log_action(ctx, "create", "user", doc["id"], email, after=out)
    return out


@router.get("/users/{user_id}")
async def get_user(user_id: str, ctx: AuthContext = Depends(require_permission("user", "view"))):
    db = get_db()
    membership = await db.user_company_roles.count_documents(
        {"user_id": user_id, "company_id": ctx.company_id, "status": "active"}
    )
    if not membership and not ctx.is_super_admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna tidak ditemukan di perusahaan aktif Anda.")
    user = serialize(await db.users.find_one({"id": user_id}, NO_ID))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna tidak ditemukan.")
    rows = await db.user_company_roles.find({"user_id": user_id, "status": "active"}, NO_ID).to_list(500)
    if not ctx.is_platform_admin:
        # Isolasi tenant: keanggotaan user di tenant lain tidak ditampilkan.
        rows = [r for r in rows if r.get("company_id") == ctx.company_id]
    out = _public(user)
    out["role_keys"] = sorted({r["role_key"] for r in rows if r.get("company_id") == ctx.company_id})
    out["memberships"] = serialize_list(rows)
    return out


@router.put("/users/{user_id}")
async def update_user(
    user_id: str, payload: UserUpdate, ctx: AuthContext = Depends(require_permission("user", "edit"))
):
    db = get_db()
    before = serialize(await db.users.find_one({"id": user_id}, NO_ID))
    if not before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna tidak ditemukan.")
    membership = await db.user_company_roles.count_documents(
        {"user_id": user_id, "company_id": ctx.company_id, "status": "active"}
    )
    if not membership and not ctx.is_super_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Pengguna ini bukan anggota perusahaan aktif Anda."
        )
    await _guard_platform_user(ctx, user_id)

    data = payload.model_dump(exclude_none=True)
    # Akun yang juga dipakai di tenant lain: Tenant Admin hanya boleh mengatur PERAN
    # di tenant-nya. Data akun global (password, status, profil) hanya oleh Platform Admin.
    account_fields = [
        k for k in data if k != "role_keys" and (k == "password" or data[k] != (before or {}).get(k))
    ]
    if account_fields and not ctx.is_platform_admin and await _has_other_tenant_membership(ctx, user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Akun ini juga terdaftar di tenant lain. Tenant Admin hanya dapat mengatur peran di tenant ini; "
            "perubahan data akun (kata sandi, status, profil) dilakukan oleh Platform Admin.",
        )
    role_keys = data.pop("role_keys", None)
    new_password = data.pop("password", None)
    if new_password:
        data["password_hash"] = hash_password(new_password)
        data["must_change_password"] = True
    if data:
        data.update(audit_fields(ctx.user_id, creating=False))
        await db.users.update_one({"id": user_id}, {"$set": data})

    if role_keys is not None:
        assignable = await _assignable_role_keys(ctx)
        invalid = [r for r in role_keys if r not in assignable]
        if invalid:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Peran berikut tidak dapat Anda berikan: {', '.join(invalid)}.",
            )
        if not role_keys:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Pengguna harus memiliki minimal satu peran di perusahaan ini.",
            )
        await db.user_company_roles.delete_many({"user_id": user_id, "company_id": ctx.company_id})
        for rk in role_keys:
            await db.user_company_roles.insert_one(
                {
                    "id": new_id(),
                    "user_id": user_id,
                    "company_id": ctx.company_id,
                    "role_key": rk,
                    "status": "active",
                    **audit_fields(ctx.user_id, creating=True),
                }
            )

    after = serialize(await db.users.find_one({"id": user_id}, NO_ID))
    rows = await db.user_company_roles.find(
        {"user_id": user_id, "company_id": ctx.company_id, "status": "active"}, NO_ID
    ).to_list(100)
    out = _public(after)
    out["role_keys"] = sorted({r["role_key"] for r in rows})
    await log_action(ctx, "update", "user", user_id, after.get("email"), before=before, after=after)
    return out


@router.delete("/users/{user_id}")
async def remove_user_from_company(
    user_id: str, ctx: AuthContext = Depends(require_permission("user", "delete"))
):
    if user_id == ctx.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Anda tidak dapat menghapus akses diri sendiri.")
    db = get_db()
    user = serialize(await db.users.find_one({"id": user_id}, NO_ID))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna tidak ditemukan.")
    await _guard_platform_user(ctx, user_id)
    result = await db.user_company_roles.delete_many({"user_id": user_id, "company_id": ctx.company_id})
    if result.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna ini bukan anggota perusahaan aktif Anda.")
    await log_action(
        ctx, "revoke_access", "user", user_id, user.get("email"), before=user,
        notes="Akses pengguna dicabut dari perusahaan aktif",
    )
    return {"message": f"Akses {user.get('full_name')} pada perusahaan ini berhasil dicabut."}


@router.post("/users/{user_id}/grant-company-access")
async def grant_company_access(
    user_id: str,
    payload: Dict[str, Any] = Body(...),
    ctx: AuthContext = Depends(require_permission("user", "edit")),
):
    """Give an existing account access to another company (multi-company user)."""
    db = get_db()
    target_company = payload.get("company_id")
    role_keys = payload.get("role_keys") or []
    if not target_company or not role_keys:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Perusahaan dan peran wajib dipilih.")
    # Akses lintas tenant = kewenangan platform. Tenant Admin tidak dapat
    # memberikan (atau memindahkan) akses ke tenant lain.
    if not ctx.is_platform_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Pemberian akses ke tenant lain hanya dapat dilakukan oleh Platform Admin.",
        )
    user = serialize(await db.users.find_one({"id": user_id}, NO_ID))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pengguna tidak ditemukan.")
    await db.user_company_roles.delete_many({"user_id": user_id, "company_id": target_company})
    for rk in role_keys:
        await db.user_company_roles.insert_one(
            {
                "id": new_id(),
                "user_id": user_id,
                "company_id": target_company,
                "role_key": rk,
                "status": "active",
                **audit_fields(ctx.user_id, creating=True),
            }
        )
    await log_action(
        ctx, "grant_access", "user", user_id, user.get("email"),
        after={"company_id": target_company, "role_keys": role_keys},
        notes="Akses perusahaan tambahan diberikan",
    )
    return {"message": f"Akses perusahaan berhasil diberikan kepada {user.get('full_name')}."}


# ------------------------------------------------------------------- roles
@router.get("/roles")
async def list_roles(ctx: AuthContext = Depends(require_permission("role", "view"))):
    db = get_db()
    roles = [
        r for r in serialize_list(await db.roles.find({}, NO_ID).sort("sort_order", 1).to_list(500))
        if _role_visible(ctx, r)
    ]
    perms = await db.role_permissions.find({}, NO_ID).to_list(20000)
    by_role: Dict[str, List[str]] = {}
    for p in perms:
        by_role.setdefault(p["role_key"], []).append(p["permission_key"])
    for r in roles:
        r["permission_keys"] = sorted(by_role.get(r["key"], []))
        r["permission_count"] = len(r["permission_keys"])
        r["is_global"] = r.get("company_id") is None
        r["editable"] = ctx.is_platform_admin or not r["is_global"]
        r["user_count"] = await db.user_company_roles.count_documents(
            {"role_key": r["key"], "company_id": ctx.company_id, "status": "active"}
        )
    return {"items": roles, "total": len(roles)}


@router.get("/permissions")
async def list_permissions(ctx: AuthContext = Depends(require_permission("role", "view"))):
    db = get_db()
    rows = serialize_list(
        await db.permissions.find({}, NO_ID).sort([("resource", 1), ("action", 1)]).to_list(2000)
    )
    return {"items": rows, "total": len(rows)}


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(payload: RoleCreate, ctx: AuthContext = Depends(require_permission("role", "create"))):
    db = get_db()
    if await db.roles.count_documents({"key": payload.key}):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Kode peran '{payload.key}' sudah digunakan.")
    last = await db.roles.find({}, NO_ID).sort("sort_order", -1).limit(1).to_list(1)
    doc = {
        "id": new_id(),
        # Platform Admin membuat peran global; Tenant Admin membuat peran khusus tenant-nya.
        "company_id": None if ctx.is_platform_admin else ctx.company_id,
        "key": payload.key,
        "name": payload.name,
        "description": payload.description,
        "is_system": False,
        "scope": "company",
        "sort_order": (last[0]["sort_order"] + 1) if last else 100,
        "status": "active",
    }
    doc.update(audit_fields(ctx.user_id, creating=True))
    await db.roles.insert_one(dict(doc))
    clean = {k: v for k, v in doc.items() if k != "_id"}
    await log_action(ctx, "create", "role", doc["id"], payload.name, after=clean)
    return clean


@router.put("/roles/{role_key}")
async def update_role(
    role_key: str, payload: RoleUpdate, ctx: AuthContext = Depends(require_permission("role", "edit"))
):
    db = get_db()
    before = serialize(await db.roles.find_one({"key": role_key}, NO_ID))
    _guard_role_change(ctx, before)
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    patch.update(audit_fields(ctx.user_id, creating=False))
    await db.roles.update_one({"key": role_key}, {"$set": patch})
    after = serialize(await db.roles.find_one({"key": role_key}, NO_ID))
    await log_action(ctx, "update", "role", before["id"], after.get("name"), before=before, after=after)
    return after


@router.put("/roles/{role_key}/permissions")
async def update_role_permissions(
    role_key: str,
    payload: RolePermissionUpdate,
    ctx: AuthContext = Depends(require_permission("role", "config")),
):
    db = get_db()
    role = serialize(await db.roles.find_one({"key": role_key}, NO_ID))
    _guard_role_change(ctx, role)
    if role_key == "super_admin" and not ctx.is_super_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Hak akses Super Admin hanya dapat diubah oleh Super Admin."
        )
    if not ctx.is_platform_admin:
        forbidden = [k for k in payload.permission_keys if k == WILDCARD or k in PLATFORM_ONLY_PERMISSIONS]
        if forbidden:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Hak akses berikut khusus Platform Admin: {', '.join(forbidden)}.",
            )
    valid = {p["key"] for p in await db.permissions.find({}, NO_ID).to_list(5000)}
    valid.add("*:*")
    invalid = [k for k in payload.permission_keys if k not in valid]
    if invalid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Hak akses tidak dikenal: {', '.join(invalid[:5])}.",
        )
    before_rows = sorted(
        p["permission_key"]
        for p in await db.role_permissions.find({"role_key": role_key}, NO_ID).to_list(5000)
    )
    await db.role_permissions.delete_many({"role_key": role_key})
    for key in sorted(set(payload.permission_keys)):
        await db.role_permissions.insert_one(
            {
                "id": new_id(),
                "company_id": None,
                "role_key": role_key,
                "permission_key": key,
                "status": "active",
                **audit_fields(ctx.user_id, creating=True),
            }
        )
    await log_action(
        ctx,
        "update_permissions",
        "role",
        role["id"],
        role.get("name"),
        before={"permission_keys": before_rows},
        after={"permission_keys": sorted(set(payload.permission_keys))},
    )
    return {
        "message": f"Hak akses peran {role.get('name')} berhasil diperbarui.",
        "permission_keys": sorted(set(payload.permission_keys)),
    }


@router.delete("/roles/{role_key}")
async def delete_role(role_key: str, ctx: AuthContext = Depends(require_permission("role", "delete"))):
    db = get_db()
    role = serialize(await db.roles.find_one({"key": role_key}, NO_ID))
    _guard_role_change(ctx, role)
    if role.get("is_system"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Peran sistem tidak dapat dihapus. Anda dapat menonaktifkannya atau mengubah hak aksesnya.",
        )
    used = await db.user_company_roles.count_documents({"role_key": role_key, "status": "active"})
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Peran ini masih dipakai oleh {used} pengguna. Pindahkan pengguna tersebut terlebih dahulu.",
        )
    await db.roles.delete_one({"key": role_key})
    await db.role_permissions.delete_many({"role_key": role_key})
    await log_action(ctx, "delete", "role", role["id"], role.get("name"), before=role)
    return {"message": f"Peran {role.get('name')} berhasil dihapus."}
